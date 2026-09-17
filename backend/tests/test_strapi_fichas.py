import io

from openpyxl import Workbook

from backend.app.modules.strapi_products.fichas import FichasLookup


def test_fichas_lookup_can_read_uploaded_workbook_bytes():
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["Programa", "URL"])
    sheet.append(["Maestría en Educación - Argentina", "https://example.test/ficha.pdf"])
    output = io.BytesIO()
    workbook.save(output)

    lookup = FichasLookup(output.getvalue())

    assert lookup.find("Maestría en Educación", "Argentina") == "https://example.test/ficha.pdf"
