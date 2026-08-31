"""Genera una copia del Excel sin modificar celdas combinadas ni datos de entrada."""

import io
from openpyxl import load_workbook

from .bot_spreadsheet_service import BotSpreadsheetService


class BotReportService:
    def build(self, content: bytes, mapping: dict, results: list):
        workbook = load_workbook(io.BytesIO(content))
        service = BotSpreadsheetService()
        requested = mapping.get("lead_url") or "URL LEAD"
        inputs = {service._normalize(mapping.get(key, "")) for key in
                  ("country", "level", "program_name", "modality", "utel_url", "inconcert_url", "form_type")}
        reserved = {service._normalize(label) for label in ("RESULTADO FORMULARIO", "DETALLE BOT", "EMAIL LEAD PRUEBA", "PROGRAMA SELECCIONADO BOT")}
        if service._normalize(requested) in inputs | reserved:
            requested = "URL LEAD"
        for sheet in workbook.worksheets:
            items = [item for item in results if item["row"]["sheet"] == sheet.title]
            if not items:
                continue
            header = service._header_index(list(sheet.iter_rows(values_only=True)))
            if header is None:
                continue
            header += 1

            def column(label):
                for cell in sheet[header]:
                    if service._normalize(service._text(cell.value)) == service._normalize(label):
                        if not any(merged.min_col <= cell.column <= merged.max_col for merged in sheet.merged_cells.ranges):
                            return cell.column
                # max_column incluye celdas combinadas y columnas sin título.
                index = sheet.max_column + 1
                sheet.cell(header, index, label)
                return index

            status_col = column("RESULTADO FORMULARIO")
            detail_col = column("DETALLE BOT")
            link_col = column(requested)
            email_col = column("EMAIL LEAD PRUEBA")
            program_col = column("PROGRAMA SELECCIONADO BOT")
            for item in items:
                result = item["result"]
                row = item["row"]["row_number"]
                failure = next((s for s in result.get("stages", []) if s["status"] == "FAIL"), None)
                dry_run = result.get("dry_run", False)
                link = None if dry_run else result.get("lead_url")
                status = "ERROR"
                if result["status"] == "PASS":
                    status = "DRY RUN - NO ENVIADO" if dry_run else "EXITOSO" if link else "SIN LINK VERIFICADO"
                sheet.cell(row, status_col).value = status
                sheet.cell(row, detail_col).value = (failure["message"] if failure else result.get("summary", ""))[:32767]
                cell = sheet.cell(row, link_col)
                cell.value = link
                cell.hyperlink = link
                if link:
                    cell.style = "Hyperlink"
                sheet.cell(row, email_col).value = result.get("lead_email")
                sheet.cell(row, program_col).value = result.get("selected_program_name")
        return workbook
