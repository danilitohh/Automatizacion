import asyncio
from unittest.mock import AsyncMock

from backend.app.config.settings import Settings
from backend.app.automations.utel_inconcert.runner import UtelInconcertRunner, UtelQaError
from backend.app.schemas.bot import UtelLead, UtelQaConfig


class _SelectField:
    """Locator mínimo para probar la reparación del selector sin navegador real."""

    def __init__(self, program_name: str):
        self.program_name = program_name
        self.value = ""
        self.injected = False

    async def count(self):
        return 1

    async def input_value(self):
        return self.value

    async def evaluate(self, script, *args):
        if "tagName" in script:
            return "select"
        self.injected = True
        self.value = args[0]
        return None

    async def select_option(self, *, value):
        self.value = value


class _Form:
    def __init__(self, field):
        self.field = field

    def locator(self, selector):
        return type("Locator", (), {"first": self.field})()


def test_product_release_injects_pdp_program_missing_from_generic_select(tmp_path):
    """Una PDP validada puede completar un catálogo de formulario atrasado."""

    program = "Doctorado en Ciencia de Datos e Inteligencia Artificial"
    runner = UtelInconcertRunner(Settings(storage_dir=tmp_path))
    runner._selected_direct_page_program = program
    runner._set_dynamic_field = AsyncMock(
        side_effect=UtelQaError(
            "utel_fill",
            f"El formulario no tiene una opcion equivalente a '{program}'.",
            '[data-cy="productsInput"]',
        )
    )
    field = _SelectField(program)
    form = _Form(field)
    config = UtelQaConfig(
        country="republica dominicana",
        utel_url="https://utel.edu.mx/dominicana/doctorado-en-ciencia-de-datos-e-inteligencia-artificial",
        level="Doctorado",
        modality="En linea",
        form_type="tarjeta",
        workflow_mode="product_release",
        program_name=program,
        lead=UtelLead(),
    )

    asyncio.run(runner._recover_missing_program_selection(form, config))

    assert field.injected is True
    assert field.value == program
    assert runner.selected_program_name == program
    assert "no incluía el producto nuevo" in runner.program_selection_notice
