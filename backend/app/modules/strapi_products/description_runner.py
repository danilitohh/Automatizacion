from __future__ import annotations

from collections import Counter
from pathlib import Path
from urllib.parse import urlparse

import httpx

from ...services.logging_service import get_logger
from ...services.google_drive_client import GoogleDriveClient, GoogleDriveClientError, google_document_id
from ...services.strapi_client import StrapiAmbiguousError, StrapiClient, StrapiClientError, StrapiNotFoundError
from .models import ProductResult, ProductRow, ProductSummary
from .pdp_description import extract_content_description, extract_description, extract_program_durations, extract_subjects
from .fichas import FichasLookup


EXPERIENCE_SUFFIX = {"Argentina": "Arg", "México": "", "Mexico": "", "Colombia": "Col", "Ecuador": "Ecu", "Perú": "Per", "Peru": "Per", "Chile": "Chile", "El Salvador": "SV", "Panamá": "Pan", "Panama": "Pan", "Bolivia": "Bol", "USA": "USA", "República Dominicana": "Dom", "Republica Dominicana": "Dom"}


def experience_title(country: str) -> str:
    suffix = EXPERIENCE_SUFFIX.get(country, country)
    return f"En línea Home2026{(' ' + suffix) if suffix else ''}"


def education_level_title(program: str) -> str:
    value = program.casefold().strip()
    if value.startswith("licenciatura"):
        return "Licenciatura"
    if value.startswith("maestr"):
        return "Maestría"
    if value.startswith("doctorado"):
        return "Doctorado"
    raise ValueError(f"No se pudo determinar el nivel educativo de {program}.")


class StrapiDescriptionRunner:
    def __init__(self, client: StrapiClient, country: str, locale: str, *, dry_run: bool = True, short_field: str = "shortDescription", long_field: str = "longDescription", content_field: str = "contentDescription", programs_field: str = "programs", download_program_field: str = "downloadProgram", experience_field: str = "modalities", education_field: str = "education_level", related_products_field: str = "relatedProducts", form_education_field: str = "form_education_levels", knowledge_area_field: str = "knowledgeArea", subjects_field: str = "subjects", title_field: str = "title", status: str = "draft", google_drive_client: GoogleDriveClient | None = None, fichas_lookup: FichasLookup | None = None) -> None:
        self.client = client
        self.country = country
        self.locale = locale
        self.dry_run = dry_run
        self.short_field = short_field
        self.long_field = long_field
        self.content_field = content_field
        self.programs_field = programs_field
        self.download_program_field = download_program_field
        self.experience_field = experience_field
        self.education_field = education_field
        self.related_products_field = related_products_field
        self.form_education_field = form_education_field
        self.knowledge_area_field = knowledge_area_field
        self.subjects_field = subjects_field
        self.fichas_lookup = fichas_lookup
        self.title_field = title_field
        self.status = status
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
            content_description = extract_content_description(source, content)
            subjects = extract_subjects(source, content)
            programs_error: str | None = None
            try:
                durations = extract_program_durations(source, content)
            except ValueError as error:
                # Descriptions can still be synchronized when a PDP has no
                # two-duration Programas section; report that section without
                # inventing a second duration.
                durations = []
                programs_error = str(error)
            ficha_url = self.fichas_lookup.find(row.program, self.country) if self.fichas_lookup else None
            product = await self.client.find_product(row.program, self.locale, title_field=self.title_field, seo_field="seo", status=self.status)
            identifier = product.get("id") or product.get("documentId")
            if identifier is None:
                raise ValueError("El producto no tiene id ni documentId.")
            programs_payload: list[dict] | None = None
            if len(durations) == 2:
                existing = await self.client.get_product_programs(identifier)
                shortest, longest = durations
                program_specs = (
                    ("Programa intensivo", shortest, "Hasta 3 materias.  <br/>\nPara quienes buscan un equilibrio ideal entre su vida profesional y personal."),
                    ("Programa base", longest, "Hasta 2 materias.  <br/>\nPara quienes buscan avanzar a un ritmo constante y una carga académica más ligera."),
                )
                programs_payload = []
                for title, duration, desktop in program_specs:
                    current = next((item for item in existing if item.get("title") == title), {})
                    component = dict(current)
                    component.update({"title": title, "description": duration})
                    icon = dict(component.get("icon") or {})
                    icon["name"] = "UilClock"
                    icon.setdefault("chakraConfig", None)
                    component["icon"] = icon
                    desktop_mobile = dict(component.get("descriptionDesktopMobile") or {})
                    desktop_mobile["desktop"] = desktop
                    desktop_mobile.setdefault("mobile", None)
                    desktop_mobile.setdefault("chakraConfig", None)
                    component["descriptionDesktopMobile"] = desktop_mobile
                    programs_payload.append(component)
            download_payload = None
            if self.fichas_lookup:
                current_download = await self.client.get_product_download_program(identifier)
                download_payload = dict(current_download or {})
                download_payload["url"] = ficha_url
                button = dict(download_payload.get("buttonDownload") or {})
                button["url"] = ficha_url
                button["children"] = "Descargar ficha"
                download_payload["buttonDownload"] = button
            experience_payload = None
            if hasattr(self.client, "find_experience_option"):
                experience = await self.client.find_experience_option(experience_title(self.country), self.locale)
                experience_payload = {"id": experience.get("id")}
            metadata_payload = None
            if hasattr(self.client, "get_product_metadata_relations"):
                metadata = await self.client.get_product_metadata_relations(identifier)
                level = await self.client.find_relation_by_title("education-levels", education_level_title(row.program), self.locale)
                form_level = await self.client.find_relation_by_title("form-education-levels", education_level_title(row.program), self.locale)
                area = metadata.get(self.knowledge_area_field) or {}
                area_data = area.get("data", area)
                area_id = area_data.get("id") if isinstance(area_data, dict) else None
                metadata_payload = {
                    self.education_field: {"id": level.get("id")},
                    self.form_education_field: [{"id": form_level.get("id")}],
                    self.related_products_field: [{"id": identifier}],
                }
                if area_id is not None:
                    # Strapi expects the relation id directly for this field.
                    metadata_payload[self.knowledge_area_field] = area_id
            missing_subjects: list[str] = []
            created_subjects: list[str] = []
            subjects_payload = None
            if hasattr(self.client, "find_subject") and subjects:
                subjects_payload = []
                for subject in subjects:
                    found = await self.client.find_subject(subject, self.locale)
                    if found is None:
                        if self.dry_run:
                            missing_subjects.append(subject)
                        else:
                            found = await self.client.create_subject(subject, self.locale)
                            created_subjects.append(subject)
                            subjects_payload.append({"id": found.get("id")})
                    else:
                        subjects_payload.append({"id": found.get("id")})
            if not self.dry_run:
                attributes = {self.short_field: description, self.long_field: description, self.content_field: content_description}
                if programs_payload is not None:
                    attributes[self.programs_field] = programs_payload
                if download_payload is not None:
                    attributes[self.download_program_field] = download_payload
                if experience_payload is not None:
                    attributes[self.experience_field] = [experience_payload]
                if metadata_payload:
                    attributes.update(metadata_payload)
                if subjects_payload is not None and not missing_subjects:
                    attributes[self.subjects_field] = subjects_payload
                await self.client.update_product(identifier, attributes)
            message = f"Descripcion extraida de {source}"
            if programs_error:
                message += f"; Programas no modificados: {programs_error}"
            if missing_subjects:
                message += "; Asignaturas no encontradas: " + ", ".join(missing_subjects)
            if created_subjects:
                message += "; Asignaturas creadas: " + ", ".join(created_subjects)
            result = ProductResult(row.sheet, row.row_number, row.program, self.country, "DRY_RUN" if self.dry_run else "UPDATED", message=message, description=description)
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
