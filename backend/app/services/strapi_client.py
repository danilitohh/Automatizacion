from __future__ import annotations

import asyncio
import re
from typing import Any

import httpx


DEGREE_PREFIXES = ("licenciatura", "maestria", "maestría", "doctorado")


def searchable_program_name(program: str) -> str:
    """Remove a leading academic degree while preserving the original display name."""

    value = " ".join(str(program).strip().split())
    pattern = r"^(?:licenciatura|maestr[ií]a|doctorado)(?:\s+en)?\s+"
    remainder = re.sub(pattern, "", value, count=1, flags=re.IGNORECASE).strip()
    if remainder and remainder.casefold() != value.casefold():
        return remainder
    return value


RETRYABLE_STATUS_CODES = {408, 429, 500, 502, 503, 504}


class StrapiClientError(RuntimeError):
    def __init__(self, message: str, *, kind: str = "FAILED") -> None:
        super().__init__(message)
        self.kind = kind


class StrapiNotFoundError(StrapiClientError):
    def __init__(self, message: str) -> None:
        super().__init__(message, kind="NOT_FOUND")


class StrapiAmbiguousError(StrapiClientError):
    def __init__(self, message: str) -> None:
        super().__init__(message, kind="AMBIGUOUS")


class StrapiClient:
    def __init__(self, base_url: str, token: str, endpoint: str = "/api/products", timeout: float = 30.0, client: httpx.AsyncClient | None = None) -> None:
        if not base_url or not token:
            raise ValueError("STRAPI_URL y STRAPI_TOKEN son obligatorios.")
        self.endpoint = endpoint if endpoint.startswith("/") else f"/{endpoint}"
        self._client = client or httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            timeout=timeout,
            follow_redirects=True,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        )
        self._owns_client = client is None

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                response = await self._client.request(method, path, **kwargs)
                if response.status_code not in RETRYABLE_STATUS_CODES or attempt == 2:
                    response.raise_for_status()
                    return response
                await asyncio.sleep(0.25 * (2**attempt))
            except httpx.RequestError as error:
                last_error = error
                if attempt == 2:
                    raise StrapiClientError("No se pudo conectar con Strapi.") from error
                await asyncio.sleep(0.25 * (2**attempt))
            except httpx.HTTPStatusError as error:
                raise StrapiClientError(f"Strapi respondio HTTP {error.response.status_code}.") from error
        raise StrapiClientError("La peticion a Strapi fallo.") from last_error

    async def find_product(self, program: str, locale: str, *, title_field: str = "title", seo_field: str = "seo", status: str = "draft") -> dict[str, Any]:
        if status not in {"draft", "published"}:
            raise ValueError("El estado de contenido de Strapi debe ser draft o published.")
        names = [searchable_program_name(program)]
        if names[0].casefold() != str(program).strip().casefold():
            names.append(" ".join(str(program).strip().split()))
        for name in names:
            for include_locale in (True, False):
                params = {
                    f"filters[{title_field}][$eq]": name,
                    "status": status,
                    f"populate[{seo_field}]": "*",
                    "pagination[pageSize]": 10,
                }
                if include_locale:
                    params["locale"] = locale
                response = await self._request("GET", self.endpoint, params=params)
                entries = response.json().get("data", [])
                if not entries:
                    continue
                if len(entries) > 1:
                    raise StrapiAmbiguousError(f"La busqueda devolvio {len(entries)} registros para {name!r} / {locale}.")
                return entries[0]
        raise StrapiNotFoundError(f"No se encontro el programa {program!r} para {locale}.")

    async def update_product(self, identifier: int | str, attributes: dict[str, Any]) -> dict[str, Any]:
        response = await self._request("PUT", f"{self.endpoint}/{identifier}", json={"data": attributes})
        return response.json()

    async def get_product_programs(self, identifier: int | str) -> list[dict[str, Any]]:
        response = await self._request(
            "GET",
            f"{self.endpoint}/{identifier}",
            params={"status": "draft", "populate[programs][populate]": "*"},
        )
        data = response.json().get("data", {})
        attributes = data.get("attributes", data)
        return attributes.get("programs") or []

    async def get_product_download_program(self, identifier: int | str) -> dict[str, Any] | None:
        response = await self._request(
            "GET", f"{self.endpoint}/{identifier}",
            params={"status": "draft", "populate[downloadProgram][populate]": "*"},
        )
        data = response.json().get("data", {})
        return (data.get("attributes", data).get("downloadProgram"))

    async def find_experience_option(self, title_card: str, locale: str) -> dict[str, Any]:
        response = await self._request("GET", "/api/modalities", params={
            "filters[titleCard][$eq]": title_card, "locale": locale,
            "pagination[pageSize]": 10,
        })
        entries = response.json().get("data", [])
        if len(entries) != 1:
            raise StrapiNotFoundError(f"No se encontró una opción de experiencia única: {title_card} / {locale}.")
        return entries[0]

    async def find_relation_by_title(self, endpoint: str, title: str, locale: str) -> dict[str, Any]:
        response = await self._request("GET", f"/api/{endpoint}", params={
            "filters[title][$eq]": title, "locale": locale, "pagination[pageSize]": 10,
        })
        entries = response.json().get("data", [])
        if len(entries) != 1:
            raise StrapiNotFoundError(f"No se encontró una relación única: {title} / {locale}.")
        return entries[0]

    async def get_product_metadata_relations(self, identifier: int | str) -> dict[str, Any]:
        response = await self._request("GET", f"{self.endpoint}/{identifier}", params={
            "status": "draft", "populate[education_level]": "*",
            "populate[form_education_levels]": "*", "populate[knowledgeArea]": "*",
            "populate[relatedProducts]": "*",
        })
        data = response.json().get("data", {})
        return data.get("attributes", data)

    async def find_subject(self, title: str, locale: str) -> dict[str, Any] | None:
        for include_locale in (True, False):
            params = {"filters[title][$eq]": title, "pagination[pageSize]": 10}
            if include_locale:
                params["locale"] = locale
            response = await self._request("GET", "/api/subjects", params=params)
            entries = response.json().get("data", [])
            if entries:
                # Match the Strapi relation picker: select the first option
                # returned when duplicate titles exist.
                return entries[0]
        response = await self._request("GET", "/api/subjects", params={
            "filters[title][$containsi]": title, "pagination[pageSize]": 10,
        })
        entries = response.json().get("data", [])
        if entries:
            return entries[0]
        return None

    async def create_subject(self, title: str, locale: str) -> dict[str, Any]:
        response = await self._request("POST", "/api/subjects", json={"data": {"title": title, "locale": locale}})
        return response.json().get("data", {})

    async def update_product_programs(self, identifier: int | str, programs: list[dict[str, Any]]) -> dict[str, Any]:
        """Replace the nested Programas components while preserving component ids."""
        return await self.update_product(identifier, {"programs": programs})

    async def update_product_descriptions(
        self,
        identifier: int | str,
        short_description: str,
        long_description: str,
    ) -> dict[str, Any]:
        """Update only the two PDP description fields on a product draft."""

        return await self.update_product(
            identifier,
            {
                "shortDescription": short_description,
                "longDescription": long_description,
            },
        )

    async def update_product_content_description(self, identifier: int | str, content_description: str) -> dict[str, Any]:
        """Update only the contentDescription PDP section."""
        return await self.update_product(identifier, {"contentDescription": content_description})

