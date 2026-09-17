from __future__ import annotations

import io
import json

from openpyxl import Workbook

from .models import ProductResult, ProductSummary


def build_report(results: list[ProductResult], summary: ProductSummary) -> bytes:
    workbook = Workbook()
    detail = workbook.active
    detail.title = "Resultados"
    detail.append(["Hoja", "Fila", "Programa", "Pais", "Estado", "Canonical anterior", "Canonical nuevo", "Mensaje"])
    for result in results:
        detail.append([result.sheet, result.row_number, result.program, result.country, result.status, result.old_canonical, result.new_canonical, result.message])

    overview = workbook.create_sheet("Resumen")
    overview.append(["Metrica", "Valor"])
    for key, value in summary.as_dict().items():
        overview.append([key, value])

    output = io.BytesIO()
    workbook.save(output)
    return output.getvalue()


def build_description_report(results: list[ProductResult], summary: ProductSummary) -> bytes:
    workbook = Workbook()
    detail = workbook.active
    detail.title = "Resultados"
    detail.append(["Hoja", "Fila", "Programa", "Pais", "Estado", "siuKey", "bannerKey", "Descripcion extraida", "Cambios", "Verificacion", "Mensaje"])
    for result in results:
        detail.append([
            result.sheet, result.row_number, result.program, result.country, result.status,
            result.siu_key, result.banner_key, result.description, len(result.changes),
            result.verification.get("ok"), result.message,
        ])
    overview = workbook.create_sheet("Resumen")
    overview.append(["Metrica", "Valor"])
    for key, value in summary.as_dict().items():
        overview.append([key, value])
    overview.append(["cambios_propuestos_o_aplicados", sum(len(result.changes) for result in results)])
    overview.append(["productos_verificados", sum(result.verification.get("ok") is True for result in results)])

    plan = workbook.create_sheet("Plan por producto")
    plan.append(["Hoja", "Fila", "Programa", "Estado", "Campo", "Accion", "Antes", "Despues", "Verificado", "ID creado"])
    for result in results:
        for change in result.changes:
            before = json.dumps(change.get("before"), ensure_ascii=False, default=str) if not isinstance(change.get("before"), str) else change.get("before")
            after = json.dumps(change.get("after"), ensure_ascii=False, default=str) if not isinstance(change.get("after"), str) else change.get("after")
            plan.append([
                result.sheet, result.row_number, result.program, result.status,
                change.get("field"), change.get("action"), before, after,
                change.get("verified"), change.get("created_id"),
            ])
    output = io.BytesIO()
    workbook.save(output)
    return output.getvalue()
