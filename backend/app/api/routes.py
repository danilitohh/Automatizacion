"""Endpoints REST de la Fase 1."""

import json
from datetime import datetime

from fastapi import APIRouter, File, Form, HTTPException, Query, Request, UploadFile

from ..automations.generic_bot.runner import BotRunner
from ..database.repository import ExecutionRepository
from ..schemas.bot import BotConfig, BotRunResponse
from ..schemas.ai import AICompletionRequest, AICompletionResponse, AIProvidersResponse
from ..schemas.recorder import (
    RecorderEventsResponse,
    RecorderStartRequest,
    RecorderStartResponse,
    RecorderStopResponse,
)
from ..schemas.execution import (
    DashboardSummary,
    ExecutionListResponse,
    HealthResponse,
)
from ..services.dashboard_service import DashboardService
from ..services.ai_service import AIService
from ..services.logging_service import get_logger
from ..services.pdp_validation_service import PdpValidationService
from ..services.generic_pdp_validation_service import GenericPdpValidationService


router = APIRouter(prefix="/api")
logger = get_logger()


def dashboard_service(request: Request) -> DashboardService:
    """Obtiene el servicio a partir de la configuración guardada en la aplicación."""

    return DashboardService(request.app.state.settings.database_path)


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Permite a Electron saber si el backend local está disponible."""

    return HealthResponse(
        status="ok",
        service="qa-automation-backend",
        timestamp=datetime.now().isoformat(timespec="seconds"),
    )


@router.get("/ai/providers", response_model=AIProvidersResponse)
def ai_providers(request: Request) -> dict:
    """Indica qué proveedores de IA están configurados sin revelar secretos."""

    return {"providers": AIService(request.app.state.settings).provider_statuses()}


@router.post("/ai/generate", response_model=AICompletionResponse)
async def ai_generate(request: Request, payload: AICompletionRequest) -> dict:
    """Genera texto con el proveedor elegido para los módulos futuros."""

    try:
        completion = await AIService(request.app.state.settings).generate(
            payload.provider,
            payload.prompt,
            system_instruction=payload.system_instruction,
            model=payload.model,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except RuntimeError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    return {
        "provider": completion.provider,
        "model": completion.model,
        "text": completion.text,
        "usage": completion.usage,
        "rate_limits": completion.rate_limits,
    }


@router.get("/dashboard/summary", response_model=DashboardSummary)
def dashboard_summary(request: Request) -> dict:
    """Entrega las tarjetas y última ejecución del dashboard."""

    logger.info("Consultando resumen del dashboard")
    return dashboard_service(request).summary()


@router.get("/executions", response_model=ExecutionListResponse)
def executions(
    request: Request,
    limit: int = Query(default=20, ge=1, le=100),
) -> dict:
    """Entrega el historial paginado de forma sencilla para la Fase 1."""

    items = dashboard_service(request).history(limit)
    return {"items": items, "total": len(items)}


@router.post("/bots/run", response_model=BotRunResponse)
async def run_bot(request: Request, config: BotConfig) -> dict:
    """Ejecuta un flujo web y guarda el resultado en el historial local."""

    logger.info("Iniciando bot de formularios en segundo plano: %s", config.name)
    settings = request.app.state.settings
    result = await BotRunner(settings).run(config)
    serializable_result = {
        **result,
        "steps": [step.model_dump() for step in result["steps"]],
    }
    ExecutionRepository(settings.database_path).create_execution(
        {
            "automation_type": "generic_bot",
            "name": config.name,
            "status": "SUCCESS" if result["status"] == "PASS" else "FAIL",
            "started_at": result["started_at"],
            "finished_at": result["finished_at"],
            "duration_seconds": result["duration_seconds"],
            "summary": result["summary"],
            "error_message": None if result["status"] == "PASS" else result["summary"],
            "evidence_json": json.dumps(serializable_result, ensure_ascii=False),
            "created_at": result["finished_at"],
        }
    )
    logger.info("Bot finalizado: %s - %s", config.name, result["status"])
    return result


@router.post("/pdp/validate")
async def validate_pdp(
    request: Request,
    excel_file: UploadFile = File(...),
) -> dict:
    """Compara información de PDP en Excel/DOCX contra sus páginas web."""

    if not (excel_file.filename or "").lower().endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="Comparte un archivo Excel con extensión .xlsx.")
    if False:
        raise HTTPException(status_code=400, detail="Comparte un documento Word con extensión .docx.")

    settings = request.app.state.settings
    try:
        result = await PdpValidationService(settings).validate(
            await excel_file.read(),
        )
    except (ValueError, RuntimeError) as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    ExecutionRepository(settings.database_path).create_execution(
        {
            "automation_type": "pdp_document_validation",
            "name": f"PDP vs DOCX ({result['summary']['programs']} programas)",
            "status": "SUCCESS" if result["status"] == "PASS" else "WARNING",
            "started_at": result["started_at"],
            "finished_at": result["finished_at"],
            "duration_seconds": result["duration_seconds"],
            "summary": (
                f"{result['summary']['programs']} PDP revisadas · "
                f"{result['summary']['failed']} secciones con diferencias."
            ),
            "error_message": None,
            "evidence_json": json.dumps(result, ensure_ascii=False),
            "created_at": result["finished_at"],
        }
    )
    return result


@router.post("/pdp/semantic-validate")
async def validate_pdp_semantic(
    request: Request,
    source_file: UploadFile = File(...),
    url: str = Form(...),
    use_ai: bool = Form(True),
) -> dict:
    """Compara cualquier documento admitido contra una única pÃ¡gina PDP."""

    settings = request.app.state.settings
    try:
        result = await GenericPdpValidationService(settings).validate(
            source_file.filename or "fuente",
            await source_file.read(),
            url.strip(),
            use_ai,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except RuntimeError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error

    summary = result["summary"]
    ExecutionRepository(settings.database_path).create_execution(
        {
            "automation_type": "pdp_semantic_validation",
            "name": f"PDP vs {result['source_filename']}",
            "status": "SUCCESS" if result["status"] == "PASS" else "WARNING",
            "started_at": result["started_at"],
            "finished_at": result["finished_at"],
            "duration_seconds": result["duration_seconds"],
            "summary": f"{summary['exact_matches'] + summary['normalized_matches']} coincidentes Â· {summary['missing']} faltantes Â· {summary['different']} diferentes.",
            "error_message": None,
            "evidence_json": json.dumps(result, ensure_ascii=False),
            "created_at": result["finished_at"],
        }
    )
    return result


@router.post("/bots/recorder/start", response_model=RecorderStartResponse)
async def start_bot_recorder(request: Request, config: RecorderStartRequest) -> dict:
    """Abre un navegador visible y comienza a capturar interacciones."""

    try:
        session = await request.app.state.recorder_manager.start(request.app.state.settings, config)
    except RuntimeError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return {"session_id": session.session_id, "status": "RECORDING", "url": config.url}


@router.get("/bots/recorder/{session_id}/events", response_model=RecorderEventsResponse)
async def recorder_events(request: Request, session_id: str) -> dict:
    """Entrega los eventos que el navegador ha capturado hasta este momento."""

    session = request.app.state.recorder_manager.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="La sesión de grabación no existe.")
    return {"events": session.get_events(), "active": session.active, "error": session.error}


@router.post("/bots/recorder/{session_id}/stop", response_model=RecorderStopResponse)
async def stop_bot_recorder(request: Request, session_id: str) -> dict:
    """Cierra la grabación y devuelve pasos listos para el constructor."""

    session = request.app.state.recorder_manager.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="La sesión de grabación no existe.")
    steps = await request.app.state.recorder_manager.stop(session_id)
    return {"status": "STOPPED", "url": session.config.url, "steps": steps}
