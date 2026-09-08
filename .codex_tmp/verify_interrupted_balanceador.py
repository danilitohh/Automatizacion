import asyncio
import json

from backend.app.automations.utel_inconcert.runner import UtelInconcertRunner
from backend.app.config.settings import get_settings
from backend.app.schemas.bot import UtelLead, UtelQaConfig


CASES = [
    {
        "row": 22,
        "program": "Licenciatura en Ingeniería en Programación en la Nube",
        "url": "https://utel.edu.mx/argentina/licenciatura-en-ingenieria-en-programacion-en-la-nube",
        "name": "Danilo Prueba ARB",
        "email": "Testing2026-09-07N187@testingUtel.com",
        "phone": "1111111119",
    },
    {
        "row": 26,
        "program": "Licenciatura en Tecnologías Interactivas y Experiencia e Interfaz de Usuario",
        "url": "https://utel.edu.mx/argentina/licenciatura-en-tecnologias-interactivas-y-experiencia-e-interfaz-de-usuario",
        "name": "Danilo Prueba ARF",
        "email": "Testing2026-09-07N191@testingUtel.com",
        "phone": "1142440183",
    },
]


async def main() -> None:
    settings = get_settings()
    for case in CASES:
        config = UtelQaConfig(
            name=f"Verificación Balanceador fila {case['row']}",
            environment="sandbox",
            dry_run=False,
            country="Argentina",
            utel_url=case["url"],
            inconcert_url=settings.lead_balancer_url,
            lead_origin_url=settings.lead_balancer_url,
            lead_search_destination="balanceador",
            modality="En linea",
            level="Licenciatura",
            form_type="tarjeta",
            program_selection_strategy="exact_match",
            program_name=case["program"],
            browser="chrome",
            headless=False,
            keep_browser_open=False,
            workflow_mode="product_release",
            verification_only=True,
            lead=UtelLead(
                name=case["name"], email=case["email"], phone=case["phone"]
            ),
        )
        result = await UtelInconcertRunner(settings).run(config)
        failed_stage = next(
            (stage for stage in result["stages"] if stage.status == "FAIL"), None
        )
        print(
            json.dumps(
                {
                    "row": case["row"],
                    "status": result["status"],
                    "lead_url": result.get("lead_url"),
                    "lead_found": result.get("lead_found"),
                    "summary": result.get("summary"),
                    "failure": failed_stage.model_dump() if failed_stage else None,
                },
                ensure_ascii=False,
            ),
            flush=True,
        )


if __name__ == "__main__":
    asyncio.run(main())
