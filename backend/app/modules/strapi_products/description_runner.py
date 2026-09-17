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
from .common_questions import build_common_questions_payload, common_questions_match, extract_common_questions
from .bullet_tabs import TAB_PREFIXES, build_bullet_tab_payload, extract_bullet_tabs, has_desktop_cover_image, linked_tab_prefix
from .fichas import FichasLookup
from .balancer_catalog import BalancerCatalogError
from .sync_plan import payload_matches, plan_change
from .schema_validation import validate_product_payload


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
    def __init__(self, client: StrapiClient, country: str, locale: str, *, dry_run: bool = True, short_field: str = "shortDescription", long_field: str = "longDescription", content_field: str = "contentDescription", programs_field: str = "programs", download_program_field: str = "downloadProgram", experience_field: str = "modalities", education_field: str = "education_level", related_products_field: str = "relatedProducts", form_education_field: str = "form_education_levels", knowledge_area_field: str = "knowledgeArea", subjects_field: str = "subjects", siu_key_field: str = "siuKey", banner_key_field: str = "bannerKey", siu_key_lookup=None, title_field: str = "title", status: str = "draft", google_drive_client: GoogleDriveClient | None = None, fichas_lookup: FichasLookup | None = None, product_schema: dict | None = None) -> None:
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
        self.siu_key_field = siu_key_field
        self.banner_key_field = banner_key_field
        self.siu_key_lookup = siu_key_lookup
        self.fichas_lookup = fichas_lookup
        self.product_schema = product_schema
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
        changes: list[dict] = []
        verification: dict = {"ok": None, "performed": False}
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
            common_questions_payload = None
            faq_matches = None
            faq_entries = extract_common_questions(source, content)
            if faq_entries is not None and hasattr(self.client, "get_product_common_questions"):
                current_faq = await self.client.get_product_common_questions(identifier, self.locale)
                faq_matches = common_questions_match(faq_entries, current_faq)
                common_questions_payload = build_common_questions_payload(faq_entries, current_faq)
            siu_key = await self.siu_key_lookup(row.program) if self.siu_key_lookup else None
            tabs_bullet_section_payload = None
            bullet_tab_operations = []
            manages_bullet_tabs = all(
                hasattr(self.client, name)
                for name in (
                    "get_bullet_tab_by_id", "find_bullet_tab_template",
                    "create_bullet_tab", "update_bullet_tab",
                )
            )
            if manages_bullet_tabs and hasattr(self.client, "get_product_tabs_bullet_section"):
                bullet_tab_sections = extract_bullet_tabs(source, content)
                section = await self.client.get_product_tabs_bullet_section(identifier, self.locale)
                tab_ids = []
                for tab_prefix in TAB_PREFIXES:
                    tab_name = f"{tab_prefix} {row.program}"
                    linked_matches = [
                        item for item in (section.get("tabs") or [])
                        if item.get("id") is not None
                        and linked_tab_prefix(item.get("strapiName") or "", row.program) == tab_prefix
                    ]
                    if len(linked_matches) > 1:
                        raise StrapiAmbiguousError(f"El producto tiene varias pestañas relacionadas para {tab_prefix!r}.")
                    existing_tab = (
                        await self.client.get_bullet_tab_by_id(linked_matches[0]["id"])
                        if linked_matches else None
                    )
                    if existing_tab is None and hasattr(self.client, "find_localized_bullet_tab_by_strapi_name"):
                        existing_tab = await self.client.find_localized_bullet_tab_by_strapi_name(tab_name, self.locale)
                    template = None
                    if existing_tab is None or (
                        tab_prefix == "Perfil egreso" and not has_desktop_cover_image(existing_tab)
                    ):
                        template = await self.client.find_bullet_tab_template(tab_prefix, self.locale)
                    payload = build_bullet_tab_payload(
                        row.program, bullet_tab_sections[tab_prefix],
                        existing=existing_tab, template=template, locale=self.locale,
                    )
                    bullet_tab_operations.append((existing_tab, payload, tab_name))
                    tab_id = existing_tab.get("id") if existing_tab else None
                    tab_ids.append({"id": tab_id} if tab_id is not None else None)
                tabs_bullet_section_payload = {
                    "idForScrolling": "bannerSectionPdp",
                    "hideSection": section.get("hideSection", False),
                }
                if section.get("id") is not None:
                    tabs_bullet_section_payload["id"] = section["id"]
                if all(tab_ids):
                    tabs_bullet_section_payload["tabs"] = tab_ids
            elif hasattr(self.client, "get_product_tabs_bullet_section") and hasattr(self.client, "find_bullet_tab_by_strapi_name"):
                section = await self.client.get_product_tabs_bullet_section(identifier, self.locale)
                tabs = []
                for tab_prefix in TAB_PREFIXES:
                    tab = await self.client.find_bullet_tab_by_strapi_name(
                        f"{tab_prefix} {row.program}", self.locale
                    )
                    if tab.get("id") is None:
                        raise StrapiNotFoundError(f"La pestaña {tab_prefix!r} no tiene un id válido.")
                    tabs.append({"id": tab["id"]})
                tabs_bullet_section_payload = {
                    "idForScrolling": "bannerSectionPdp",
                    "hideSection": section.get("hideSection", False),
                    "tabs": tabs,
                }
                if section.get("id") is not None:
                    tabs_bullet_section_payload["id"] = section["id"]
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
            subject_changes: list[dict] = []
            subjects_payload = None
            if hasattr(self.client, "find_subject") and subjects:
                subjects_payload = []
                for subject in subjects:
                    found = await self.client.find_subject(subject, self.locale)
                    if found is None:
                        if self.dry_run:
                            missing_subjects.append(subject)
                            subject_changes.append(plan_change(f"{self.subjects_field}.{subject}", None, subject, action="create"))
                        else:
                            found = await self.client.create_subject(subject, self.locale)
                            created_subjects.append(subject)
                            subject_change = plan_change(f"{self.subjects_field}.{subject}", None, subject, action="create")
                            subject_change["created_id"] = found.get("id")
                            subject_changes.append(subject_change)
                            subjects_payload.append({"id": found.get("id")})
                    else:
                        subjects_payload.append({"id": found.get("id")})
            current_attributes = (
                await self.client.get_product_sync_attributes(identifier, self.locale)
                if hasattr(self.client, "get_product_sync_attributes")
                else product.get("attributes", product)
            )
            changes.extend(subject_changes)

            tab_changes: list[tuple[dict | None, dict, str, bool]] = []
            for existing_tab, payload, tab_name in bullet_tab_operations:
                matches = bool(existing_tab) and payload_matches(
                    existing_tab.get("attributes", existing_tab), payload
                )
                if not matches:
                    action = "update" if existing_tab else "create"
                    before = (existing_tab or {}).get("attributes", existing_tab or {}).get("content")
                    changes.append(plan_change(f"tabsBulletSection.{tab_name}", before, payload.get("content"), action=action))
                    tab_changes.append((existing_tab, payload, tab_name, True))
                else:
                    tab_changes.append((existing_tab, payload, tab_name, False))

            persisted_tab_ids: list[dict[str, int | str]] = (
                list((tabs_bullet_section_payload or {}).get("tabs") or [])
                if not manages_bullet_tabs else []
            )
            verification_tabs: list[tuple[int | str, dict, str]] = []
            for existing_tab, _, tab_name, _ in tab_changes:
                tab_id = existing_tab.get("id") if existing_tab else None
                persisted_tab_ids.append({"id": tab_id} if tab_id is not None else {"name": tab_name})

            attributes = {self.short_field: description, self.long_field: description, self.content_field: content_description}
            attributes["customLayoutPDP"] = "thirdLayout"
            if common_questions_payload is not None and faq_matches is False:
                attributes["commonQuestions"] = common_questions_payload
            if tabs_bullet_section_payload is not None:
                section_payload = dict(tabs_bullet_section_payload)
                if all("id" in item for item in persisted_tab_ids):
                    section_payload["tabs"] = persisted_tab_ids
                    attributes["tabsBulletSection"] = section_payload
            if siu_key is not None:
                attributes[self.siu_key_field] = siu_key
                attributes[self.banner_key_field] = siu_key
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

            schema_errors = validate_product_payload(attributes, self.product_schema)
            if schema_errors:
                raise ValueError("Payload PDP incompatible con el esquema capturado de Strapi: " + "; ".join(schema_errors))

            update_attributes: dict = {}
            for field_name, desired in attributes.items():
                current = current_attributes.get(field_name)
                if not payload_matches(current, desired):
                    update_attributes[field_name] = desired
                    changes.append(plan_change(field_name, current, desired))

            if tabs_bullet_section_payload is not None and self.dry_run and any(
                existing_tab is None for existing_tab, _, _, _ in tab_changes
            ):
                section_after = [
                    existing_tab.get("id") if existing_tab else tab_name
                    for existing_tab, _, tab_name, _ in tab_changes
                ]
                changes.append(plan_change(
                    "tabsBulletSection.tabs", section.get("tabs"), section_after,
                    action="link-created-tabs",
                ))

            if not self.dry_run:
                if manages_bullet_tabs:
                    persisted_tab_ids = []
                    for existing_tab, payload, tab_name, needs_write in tab_changes:
                        if needs_write:
                            if existing_tab:
                                saved = await self.client.update_bullet_tab(existing_tab["id"], payload)
                                tab_id = saved.get("id", existing_tab["id"])
                            else:
                                saved = await self.client.create_bullet_tab(payload)
                                tab_id = saved.get("id")
                            if tab_id is None:
                                raise StrapiClientError(f"Strapi no devolvió id al guardar la pestaña {tab_name!r}.")
                        else:
                            tab_id = existing_tab["id"]
                        persisted_tab_ids.append({"id": tab_id})
                        if needs_write:
                            verification_tabs.append((tab_id, payload, tab_name))

                if tabs_bullet_section_payload is not None and len(persisted_tab_ids) == len(TAB_PREFIXES):
                    section_payload = dict(tabs_bullet_section_payload)
                    section_payload["tabs"] = persisted_tab_ids
                    if not payload_matches(current_attributes.get("tabsBulletSection"), section_payload):
                        update_attributes["tabsBulletSection"] = section_payload
                        changes.append(plan_change("tabsBulletSection", current_attributes.get("tabsBulletSection"), section_payload))

                if update_attributes:
                    await self.client.update_product(identifier, update_attributes)
                verification = {"ok": True, "fields": [], "tabs": []}
                if hasattr(self.client, "get_product_sync_attributes"):
                    verified_attributes = await self.client.get_product_sync_attributes(identifier, self.locale)
                    for field_name, desired in update_attributes.items():
                        ok = payload_matches(verified_attributes.get(field_name), desired)
                        verification["fields"].append({"field": field_name, "ok": ok})
                        for item in changes:
                            if item.get("field") == field_name and item.get("action") == "update":
                                item["verified"] = ok
                        verification["ok"] = verification["ok"] and ok
                else:
                    verification["fields"] = [{"field": key, "ok": None} for key in update_attributes]
                    verification["ok"] = None
                for subject in created_subjects:
                    saved_subject = await self.client.find_subject(subject, self.locale)
                    ok = saved_subject is not None
                    verification.setdefault("subjects", []).append({"name": subject, "ok": ok})
                    for item in changes:
                        if item.get("field") == f"{self.subjects_field}.{subject}" and item.get("action") == "create":
                            item["verified"] = ok
                            if saved_subject and saved_subject.get("id") is not None:
                                item["created_id"] = saved_subject["id"]
                    verification["ok"] = (verification["ok"] is not False) and ok
                if verification_tabs:
                    for tab_id, desired, tab_name in verification_tabs:
                        saved_tab = await self.client.get_bullet_tab_by_id(tab_id)
                        ok = payload_matches(saved_tab.get("attributes", saved_tab), desired)
                        verification["tabs"].append({"name": tab_name, "id": tab_id, "ok": ok})
                        for item in changes:
                            if item.get("field") == f"tabsBulletSection.{tab_name}" and item.get("action") in {"update", "create"}:
                                item["verified"] = ok
                                if item.get("action") == "create":
                                    item["created_id"] = tab_id
                        if not ok:
                            verification["ok"] = False
                if verification.get("ok") is False:
                    failed_checks = [item for item in verification["fields"] + verification["tabs"] if item.get("ok") is False]
                    message = "Verificación posterior fallida: " + ", ".join(item["field"] for item in failed_checks if "field" in item) + ", ".join(item["name"] for item in failed_checks if "name" in item)
                    return ProductResult(row.sheet, row.row_number, row.program, self.country, "FAILED", message=message, description=description, siu_key=siu_key, banner_key=siu_key, changes=changes, verification=verification)
            else:
                verification = {"ok": None, "performed": False, "message": "Dry run: no se escribieron datos en Strapi."}
            message = f"Descripcion extraida de {source}"
            if programs_error:
                message += f"; Programas no modificados: {programs_error}"
            if missing_subjects:
                message += "; Asignaturas no encontradas: " + ", ".join(missing_subjects)
            if created_subjects:
                message += "; Asignaturas creadas: " + ", ".join(created_subjects)
            if faq_matches is not None:
                message += (
                    "; Preguntas frecuentes ya coinciden exactamente con el documento"
                    if faq_matches else
                    (
                        f"; Preguntas frecuentes se actualizarían desde el documento ({len(faq_entries)} preguntas)"
                        if self.dry_run else
                        f"; Preguntas frecuentes sincronizadas desde el documento ({len(faq_entries)} preguntas)"
                    )
                )
            if self.siu_key_lookup is None:
                message += "; siuKey no consultada: el lookup del Balanceador no está configurado"
            if self.dry_run:
                message += f"; Cambios propuestos: {len(changes)}"
            elif not changes:
                message += "; Sin cambios: Strapi ya coincide con el documento"
            result_status = "DRY_RUN" if self.dry_run else ("UPDATED" if changes else "SKIPPED")
            result = ProductResult(row.sheet, row.row_number, row.program, self.country, result_status, message=message, description=description, siu_key=siu_key, banner_key=siu_key, changes=changes, verification=verification)
            self.logger.info("Strapi descriptions result sheet=%s row=%s program=%s country=%s status=%s", row.sheet, row.row_number, row.program, self.country, result.status)
            return result
        except (StrapiNotFoundError, StrapiAmbiguousError) as error:
            status = "NOT_FOUND" if isinstance(error, StrapiNotFoundError) else "AMBIGUOUS"
            return ProductResult(row.sheet, row.row_number, row.program, self.country, status, message=str(error), changes=changes, verification=verification)
        except (ValueError, httpx.HTTPError) as error:
            self.logger.warning("Strapi descriptions invalid row=%s program=%s error=%s", row.row_number, row.program, error)
            return ProductResult(row.sheet, row.row_number, row.program, self.country, "INVALID_DATA", message=str(error), changes=changes, verification=verification)
        except StrapiClientError as error:
            return ProductResult(row.sheet, row.row_number, row.program, self.country, "FAILED", message=str(error), changes=changes, verification=verification)
        except GoogleDriveClientError as error:
            return ProductResult(row.sheet, row.row_number, row.program, self.country, "FAILED", message=str(error), changes=changes, verification=verification)
        except BalancerCatalogError as error:
            return ProductResult(row.sheet, row.row_number, row.program, self.country, "FAILED", message=str(error), changes=changes, verification=verification)

    async def run(self, rows: list[ProductRow]) -> tuple[list[ProductResult], ProductSummary]:
        results = [await self.process(row) for row in rows]
        counts = Counter(result.status for result in results)
        return results, ProductSummary(
            total=len(results), updated=counts["UPDATED"], dry_run=counts["DRY_RUN"], skipped=counts["SKIPPED"],
            not_found=counts["NOT_FOUND"], ambiguous=counts["AMBIGUOUS"], invalid_data=counts["INVALID_DATA"], failed=counts["FAILED"],
        )
