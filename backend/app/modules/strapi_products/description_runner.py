from __future__ import annotations

from collections import Counter
from pathlib import Path
from urllib.parse import urlparse

import httpx

from ...services.logging_service import get_logger
from ...services.google_drive_client import GoogleDriveClient, GoogleDriveClientError, google_document_id
from ...services.strapi_client import StrapiAmbiguousError, StrapiClient, StrapiClientError, StrapiNotFoundError
from .models import ProductResult, ProductRow, ProductSummary
from .pdp_description import extract_description


class StrapiDescriptionRunner:
    def __init__(self, client: StrapiClient, country: str, locale: str, *, dry_run: bool = True, short_field: str = "shortDescription", long_field: str = "longDescription", title_field: str = "title", google_drive_client: GoogleDriveClient | None = None) -> None:
        self.client = client
        self.country = country
        self.locale = locale
        self.dry_run = dry_run
        self.short_field = short_field
        self.long_field = long_field
        self.title_field = title_field
        self.google_drive_client = google_drive_client
        self.logger = get_logger()

    async def _document_content(self, source: str) -> tuple[str, bytes]:
        if not source:
            raise ValueError("La fila no tiene Documento PDP.")
        parsed = urlparse(source)
        if parsed.scheme in {"http", "https"} and parsed.netloc:
            document_id = google_document_id(source)
            if document_id and self.google_drive_client and self.google_drive_client.has_any_configuration and not self.google_drive_client.is_configured:
                raise GoogleDriveClientError(
                    "La configuración OAuth de Google Drive está incompleta. Define las tres variables "
                    "GOOGLE_DRIVE_CLIENT_ID, GOOGLE_DRIVE_CLIENT_SECRET y GOOGLE_DRIVE_REFRESH_TOKEN."
                )
            if document_id and self.google_drive_client and self.google_drive_client.is_configured:
                return "google-drive-document.docx", await self.google_drive_client.export_docx(document_id)
            request_url = self._google_doc_export_url(source)
            async with httpx.AsyncClient(follow_redirects=True, timeout=35) as client:
                try:
                    response = await client.get(request_url)
                    response.raise_for_status()
                except httpx.HTTPStatusError as error:
                    if document_id and error.response.status_code in {401, 403}:
                        raise GoogleDriveClientError(
                            "El documento de Google Drive es privado. Configura las credenciales OAuth "
                            "de Google Drive en .env para leerlo desde el backend."
                        ) from error
                    raise
                return "google-drive-document.docx", response.content
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
        except GoogleDriveClientError as error:
            return ProductResult(row.sheet, row.row_number, row.program, self.country, "FAILED", message=str(error))

    async def run(self, rows: list[ProductRow]) -> tuple[list[ProductResult], ProductSummary]:
        results = [await self.process(row) for row in rows]
        counts = Counter(result.status for result in results)
        return results, ProductSummary(
            total=len(results), updated=counts["UPDATED"], dry_run=counts["DRY_RUN"], skipped=counts["SKIPPED"],
            not_found=counts["NOT_FOUND"], ambiguous=counts["AMBIGUOUS"], invalid_data=counts["INVALID_DATA"], failed=counts["FAILED"],
        )
