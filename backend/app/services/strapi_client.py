from __future__ import annotations

import asyncio
from typing import Any

import httpx


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

    async def find_product(self, program: str, locale: str, *, title_field: str = "title", seo_field: str = "seo") -> dict[str, Any]:
        params = {
            f"filters[{title_field}][$eq]": program,
            "locale": locale,
            f"populate[{seo_field}]": "*",
            "pagination[pageSize]": 10,
        }
        response = await self._request("GET", self.endpoint, params=params)
        entries = response.json().get("data", [])
        if not entries:
            raise StrapiNotFoundError(f"No se encontro el programa {program!r} para {locale}.")
        if len(entries) > 1:
            raise StrapiAmbiguousError(f"La busqueda devolvio {len(entries)} registros para {program!r} / {locale}.")
        return entries[0]

    async def update_product(self, identifier: int | str, attributes: dict[str, Any]) -> dict[str, Any]:
        response = await self._request("PUT", f"{self.endpoint}/{identifier}", json={"data": attributes})
        return response.json()

