"""Planifica o aplica adiciones de hreflangs sin reemplazar los existentes."""

from __future__ import annotations

import asyncio
import re
from collections.abc import Awaitable, Callable
from typing import Any

import httpx

from ...services.strapi_client import StrapiClient
from .countries import COUNTRY_TARGETS, LOCALES, MAX_HREFLANGS, TARGETS, build_url, create_hreflang

JsonObject = dict[str, Any]


def _attributes_of(product: JsonObject) -> JsonObject:
    """Normaliza una respuesta Strapi v4/v5 a su objeto de atributos."""

    attributes = product.get("attributes")
    return attributes if isinstance(attributes, dict) else product


def _at_path(source: Any, path: str) -> Any:
    """Lee una ruta de campos con puntos sin asumir que cada objeto existe."""

    current = source
    for key in path.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _strapi_locale(locale: str) -> str:
    """Convierte el locale hreflang al casing convencional de Strapi."""

    language, country = locale.split("-", 1)
    return f"{language}-{country.upper()}"


def _identifier_of(product: JsonObject) -> str | int:
    """Obtiene el identificador que acepta el endpoint de productos."""

    identifier = product.get("documentId") or product.get("id")
    if not isinstance(identifier, (str, int)):
        raise ValueError("Producto sin documentId ni id")
    return identifier


def _slug_candidates(slug: str, locale: str) -> list[str]:
    """Busca equivalencias conocidas de licenciatura/carrera y maestría/magíster."""

    candidates = [slug]
    if locale in {"es-cl", "es-bo", "es-co", "es-ec", "es-py", "es-pe"} and re.match(r"^licenciatura(?=-|$)", slug, re.IGNORECASE):
        candidates.append("carrera" + slug[len("licenciatura"):])
    elif re.match(r"^carrera(?=-|$)", slug, re.IGNORECASE):
        candidates.append("licenciatura" + slug[len("carrera"):])
    if locale == "es-cl" and re.match(r"^maestria(?=-|$)", slug, re.IGNORECASE):
        candidates.append("magister" + slug[len("maestria"):])
    elif re.match(r"^magister(?=-|$)", slug, re.IGNORECASE):
        candidates.append("maestria" + slug[len("magister"):])
    return list(dict.fromkeys(candidates))


def _valid_slug(value: Any) -> str | None:
    """Normaliza slugs y descarta valores vacíos o que no sean texto."""

    return value.strip().strip("/") if isinstance(value, str) and value.strip() else None


def _href_langs(existing_value: Any) -> list[JsonObject]:
    """Lee las entradas existentes preservando el contenido para no borrar datos."""

    if existing_value is None:
        return []
    if not isinstance(existing_value, list):
        raise ValueError("MultipleHrefLangs no es una lista; no se modificará automáticamente.")
    if any(not isinstance(item, dict) or not isinstance(item.get("hrefLang"), str) or not item["hrefLang"].strip() for item in existing_value):
        raise ValueError("MultipleHrefLangs contiene una entrada inválida; no se eliminará automáticamente.")
    return existing_value


def _component_write_payload(attributes: JsonObject, path: str, value: Any) -> JsonObject:
    """Conserva los campos hermanos al actualizar una rama de componente."""

    keys = path.split(".")
    top = keys[0]
    if len(keys) < 2:
        raise ValueError("Actualización cancelada: la ruta debe apuntar a un campo dentro de un componente.")
    if top not in attributes or not isinstance(attributes[top], dict):
        raise ValueError(f"Actualización cancelada: Strapi no devolvió la rama {top}")
    source = attributes[top]
    updated = dict(source)
    source_cursor: Any = source
    output_cursor = updated
    for key in keys[1:-1]:
        child = source_cursor.get(key) if isinstance(source_cursor, dict) else None
        if not isinstance(child, dict):
            raise ValueError(f"Actualización cancelada: no se pudo preservar la rama {path}")
        child_copy = dict(child)
        output_cursor[key] = child_copy
        output_cursor = child_copy
        source_cursor = child
    output_cursor[keys[-1]] = value

    def media_ids(item: Any, current_path: str) -> Any:
        """Convierte relaciones de medios pobladas a IDs aceptados por Strapi."""

        if isinstance(item, list):
            return [media_ids(child, f"{current_path}[{index}]") for index, child in enumerate(item)]
        if not isinstance(item, dict):
            return item
        result = {}
        for key, child in item.items():
            field_path = f"{current_path}.{key}"
            if key.casefold() == "metaimage":
                relation = child.get("data", child) if isinstance(child, dict) else child
                if relation is None:
                    result[key] = None
                elif isinstance(relation, dict) and isinstance(relation.get("documentId") or relation.get("id"), (str, int)):
                    result[key] = relation.get("documentId") or relation.get("id")
                else:
                    raise ValueError(f"Actualización cancelada: {field_path} no tiene un ID de imagen válido")
            else:
                result[key] = media_ids(child, field_path)
        return result

    return {top: media_ids(updated, top)}


class HreflangSynchronizer:
    """Consulta equivalencias en todos los locales y limita escrituras al locale elegido."""

    def __init__(self, client: StrapiClient, *, href_langs_path: str, timeout: float, concurrency: int = 8) -> None:
        self.client = client
        self.href_langs_path = href_langs_path
        self.timeout = timeout
        self.concurrency = max(1, concurrency)
        # Reutiliza una sola sesión para comprobar URLs públicas durante el lote.
        self.web_client = httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=True,
            headers={"User-Agent": "Utel-Hreflang-Validator/1.0", "Accept": "text/html"},
        )

    async def close(self) -> None:
        """Libera la sesión de validación web al terminar el trabajo."""

        await self.web_client.aclose()

    async def _is_available(self, url: str) -> bool:
        """Solo acepta destinos públicos que respondan exactamente HTTP 200."""

        try:
            return (await self.web_client.get(url)).status_code == 200
        except httpx.HTTPError:
            return False

    async def _list_source_products(self, locale: str, page_size: int, progress: Callable[[str], None]) -> list[JsonObject]:
        """Lee todas las páginas del locale fuente en modo preview, incluyendo drafts."""

        products = []
        page = 1
        page_count = 1
        while page <= page_count:
            response = await self.client._request("GET", self.client.endpoint, params={
                "pagination[page]": page,
                "pagination[pageSize]": page_size,
                "pagination[withCount]": "true",
                "publicationState": "preview",
                "locale": locale,
                "sort": "slug:asc",
                "populate[seo][populate]": "*",
            })
            body = response.json()
            current = body.get("data")
            if not isinstance(current, list):
                raise ValueError("Strapi no devolvió una lista de productos.")
            products.extend(item for item in current if isinstance(item, dict))
            page_count = body.get("meta", {}).get("pagination", {}).get("pageCount") or page
            progress(f"Leyendo locale {locale}: página {page}/{page_count}, {len(current)} productos.")
            page += 1
        return products

    async def _find_equivalent(self, slug: str, locale: str, slug_path: str) -> tuple[JsonObject, str] | None:
        """Busca el primer producto con slug equivalente y retorna el slug real."""

        for candidate in _slug_candidates(slug, locale):
            response = await self.client._request("GET", self.client.endpoint, params={
                "locale": _strapi_locale(locale),
                "filters[slug][$eq]": candidate,
                "pagination[page]": 1,
                "pagination[pageSize]": 1,
                "publicationState": "preview",
                "populate[seo][populate]": "*",
            })
            body = response.json()
            entries = body.get("data", [])
            if isinstance(entries, list) and entries and isinstance(entries[0], dict):
                actual_slug = _valid_slug(_at_path(_attributes_of(entries[0]), slug_path)) or candidate
                return entries[0], actual_slug
        return None

    async def run(self, locale: str, *, apply: bool, max_products: int | None, page_size: int, progress: Callable[[str], None]) -> list[JsonObject]:
        """Construye y reporta cambios; solo hace PUT cuando apply es verdadero."""

        if locale not in LOCALES:
            raise ValueError("Selecciona uno de los locales disponibles.")
        source_locale = _strapi_locale(locale)
        products = await self._list_source_products(source_locale, page_size, progress)
        sources = []
        for product in products:
            attrs = _attributes_of(product)
            slug = _valid_slug(_at_path(attrs, "slug"))
            if slug:
                sources.append((product, slug))
        if max_products:
            sources = sources[:max_products]
        progress(f"Fuente lista: {len(sources)} productos para {source_locale}.")

        gate = asyncio.Semaphore(self.concurrency)

        async def lookup(target_locale: str, source: JsonObject, slug: str) -> tuple[str, tuple[JsonObject, str] | None]:
            if target_locale == locale:
                return target_locale, (source, slug)
            async with gate:
                return target_locale, await self._find_equivalent(slug, target_locale, "slug")

        results = []
        for index, (source, slug) in enumerate(sources, start=1):
            attributes = _attributes_of(source)
            identifier = _identifier_of(source)
            name = attributes.get("title") if isinstance(attributes.get("title"), str) else slug
            siu_key = attributes.get("siuKey")
            try:
                checks = await asyncio.gather(*(lookup(target.hreflang, source, slug) for target in COUNTRY_TARGETS))
                matches = {code: match for code, match in checks if match}
                unavailable = [
                    {"hreflang": code, "reason": "No existe producto equivalente en Strapi"}
                    for code, match in checks if not match
                ]
                # Evita crear referencias hreflang hacia páginas no publicadas o caídas.
                async def check_target(code: str, match: tuple[JsonObject, str]) -> tuple[str, tuple[JsonObject, str] | None]:
                    target = next(item for item in TARGETS if item.hreflang == code)
                    url = build_url(target, match[1])
                    async with gate:
                        return code, match if await self._is_available(url) else None

                checked = await asyncio.gather(*(check_target(code, match) for code, match in matches.items()))
                for code, match in checked:
                    if match is None:
                        unavailable.append({"hreflang": code, "reason": "La URL pública no respondió HTTP 200"})
                        matches.pop(code, None)
                mexico = matches.get("es-mx")
                desired = []
                if mexico:
                    mx_target = next(target for target in TARGETS if target.hreflang == "es-mx")
                    desired.append(create_hreflang("x-default", build_url(mx_target, mexico[1])))
                else:
                    unavailable.insert(0, {"hreflang": "x-default", "reason": "No existe producto equivalente en es-mx"})
                for code, (_, matched_slug) in matches.items():
                    target = next(item for item in TARGETS if item.hreflang == code)
                    desired.append(create_hreflang(code, build_url(target, matched_slug)))

                existing = _href_langs(_at_path(attributes, self.href_langs_path))
                existing_codes = {str(item["hrefLang"]).strip().casefold() for item in existing}
                additions = [item for item in desired if item["hrefLang"].casefold() not in existing_codes]
                additions = additions[:max(0, MAX_HREFLANGS - len(existing))]
                final_value = [*existing, *additions]
                action = "unchanged" if not additions else "updated" if apply else "would-update"
                if apply and additions:
                    payload = _component_write_payload(attributes, self.href_langs_path, final_value)
                    await self.client._request("PUT", f"{self.client.endpoint}/{identifier}", params={"locale": source_locale}, json={"data": payload})
                results.append({
                    "identifier": identifier, "locale": source_locale, "slug": slug,
                    "product_name": name, "siu_key": str(siu_key or ""),
                    "href_langs": final_value, "added": additions, "unavailable": unavailable,
                    "action": action,
                })
            except Exception as error:  # noqa: BLE001 - un producto fallido no detiene el lote.
                results.append({
                    "identifier": identifier, "locale": source_locale, "slug": slug,
                    "product_name": name, "siu_key": str(siu_key or ""),
                    "href_langs": [], "added": [], "unavailable": [],
                    "action": "error", "error": str(error),
                })
            progress(f"{index}/{len(sources)} · {slug} · {results[-1]['action']}")
        return results


