from __future__ import annotations

from collections import Counter
from pathlib import Path
from urllib.parse import urlparse

import httpx

from ...services.logging_service import get_logger
from ...services.strapi_client import StrapiAmbiguousError, StrapiClient, StrapiClientError, StrapiNotFoundError
from .models import ProductResult, ProductRow, ProductSummary
from .pdp_description import extract_description


class StrapiDescriptionRunner:
    def __init__(self, client: StrapiClient, country: str, locale: str, *, dry_run: bool = True, short_field: str = "shortDescription", long_field: str = "longDescription", title_field: str = "title") -> None:
        self.client = client
        self.country = country
        self.locale = locale
        self.dry_run = dry_run
        self.short_field = short_field
        self.long_field = long_field
        self.title_field = title_field
        self.logger = get_logger()

    async def _document_content(self, source: str) -> tuple[str, bytes]:
        if not source:
            raise ValueError("La fila no tiene Documento PDP.")
        parsed = urlparse(source)
        if parsed.scheme in {"http", "https"} and parsed.netloc:
            request_url = self._google_doc_export_url(source)
            async with httpx.AsyncClient(follow_redirects=True, timeout=35) as client:
                response = await client.get(request_url)
                response.raise_for_status()
                return request_url, response.content
        path = Path(source.strip('\\"'))
        if not path.is_file():
            raise ValueError(f"No se encontro el Documento PDP: {source}")
        return str(path), path.read_bytes()

    @staticmethod
    def _google_doc_export_url(source: str) -> str:
        """Convert a Google Docs edit/share URL to a downloadable DOCX URL."""
        parsed = urlparse(source)
        if parsed.netloc.casefold() not in {"docs.google.com", "drive.google.com"}:
            return source
        parts = [part for part in parsed.path.split("/") if part]
        try:
            document_index = parts.index("document")
            if parts[document_index + 1] != "d":
                return source
            document_id = parts[document_index + 2]
        except (ValueError, IndexError):
            return source
        return f"https://docs.google.com/document/d/{document_id}/export?format=docx"

    async def process(self, row: ProductRow) -> ProductResult:
        try:
            source, content = await self._document_content(row.document or "")
            description = extract_description(row.program, source, content)
            product = await self.client.find_product(row.program, self.locale, title_field=self.title_field, seo_field="seo")
            identifier = product.get("id") or product.get("documentId")
            if identifier is None:
                raise ValueError("El producto no tiene id ni documentId.")
            if not self.dry_run:
                await self.client.update_product(identifier, {self.short_field: description, self.long_field: description})
            result = ProductResult(row.sheet, row.row_number, row.program, self.country, "DRY_RUN" if self.dry_run else "UPDATED", message=f"Descripcion extraida de {source}", description=description)
            self.logger.info("Strapi descriptions result sheet=%s row=%s program=%s country=%s status=%s", row.sheet, row.row_number, row.program, self.country, result.status)
            return result
        except (StrapiNotFoundError, StrapiAmbiguousError) as error:
            status = "NOT_FOUND" if isinstance(error, StrapiNotFoundError) else "AMBIGUOUS"
            return ProductResult(row.sheet, row.row_number, row.program, self.country, status, message=str(error))
        except (ValueError, httpx.HTTPError) as error:
            self.logger.warning("Strapi descriptions invalid row=%s program=%s error=%s", row.row_number, row.program, error)
            return ProductResult(row.sheet, row.row_number, row.program, self.country, "INVALID_DATA", message=str(error))
        except StrapiClientError as error:
            return ProductResult(row.sheet, row.row_number, row.program, self.country, "FAILED", message=str(error))

    async def run(self, rows: list[ProductRow]) -> tuple[list[ProductResult], ProductSummary]:
        results = [await self.process(row) for row in rows]
        counts = Counter(result.status for result in results)
        return results, ProductSummary(
            total=len(results), updated=counts["UPDATED"], dry_run=counts["DRY_RUN"], skipped=counts["SKIPPED"],
            not_found=counts["NOT_FOUND"], ambiguous=counts["AMBIGUOUS"], invalid_data=counts["INVALID_DATA"], failed=counts["FAILED"],
        )
