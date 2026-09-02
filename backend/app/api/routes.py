"""Endpoints REST de la Fase 1."""

import json
import asyncio
import os
from datetime import datetime
from uuid import uuid4
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse

from ..automations.generic_bot.runner import BotRunner
from ..automations.utel_inconcert.runner import UtelInconcertRunner
from ..automations.weekly_auto.runner import WeeklyAutoRunner
from ..database.repository import ExecutionRepository
from ..schemas.bot import (
    BotConfig,
    BotJobResponse,
    BotRunResponse,
    BotStartResponse,
    UtelQaConfig,
    UtelQaJobResponse,
)
from ..schemas.weekly_auto import (
    WeeklyAutoConfig,
    WeeklyAutoJobResponse,
)
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
from ..services.bot_spreadsheet_service import BotSpreadsheetService
from ..services.bot_report_service import BotReportService
from ..services.test_lead_service import TestLeadService


router = APIRouter(prefix="/api")


def _save_utel_batch_report(
    settings: Any,
    job_id: str,
    filename: str,
    content: bytes,
    mapping: dict[str, Any],
    results: list[dict[str, Any]],
) -> None:
    """Guarda un checkpoint descargable, incluso mientras el lote sigue activo."""

    if not results:
        return
    output_dir = settings.storage_dir / "reports" / "bot"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{job_id}_{filename.rsplit('.', 1)[0]}.xlsx"
    BotReportService().build(content, mapping, results).save(output_path)


@router.get("/runtime")
def backend_runtime() -> dict:
    """Permite a Electron reconocer su proceso, sin exponer secretos."""
    return {"instance_id": os.environ.get("QA_BACKEND_INSTANCE", ""), "pid": os.getpid()}


@router.post("/bots/utel-inconcert/spreadsheet-preview")
async def preview_bot_spreadsheet(file: UploadFile = File(...)) -> dict:
    """Analiza hojas Excel y propone un mapeo flexible para el Bot."""

    if not (file.filename or "").lower().endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="Comparte un archivo Excel con extensión .xlsx.")
    try:
        return BotSpreadsheetService().preview(await file.read(), file.filename or "archivo.xlsx")
    except asyncio.CancelledError:
        job.update({"status": "CANCELLED", "finished_at": datetime.now().isoformat(timespec="seconds"), "summary": "Lote detenido por el usuario."})
        raise
    except Exception as error:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"No fue posible analizar el Excel: {error}") from error


async def _run_utel_batch_job(application, job_id: str, content: bytes, filename: str, raw_config: dict, mapping: dict[str, str]) -> None:
    """Ejecuta las filas seleccionadas y escribe URL LEAD en una copia del Excel."""

    settings = application.state.settings
    job = application.state.utel_batch_jobs[job_id]
    inter_row_delay = max(0, int(settings.batch_delay_seconds))
    results: list[dict[str, Any]] = []
    logger.info("Lote %s con pausa anti-bloqueo entre filas: %ss", job_id, inter_row_delay)
    try:
        service = BotSpreadsheetService()
        rows = service.rows_for_mapping(content, mapping)
        selected_rows = {
            (str(item.get("sheet")), int(item.get("row_number")))
            for item in mapping.get("selected_rows", [])
            if item.get("sheet") and item.get("row_number") is not None
        }
        selected_sheet = mapping.get("selected_sheet")
        selected_row_number = mapping.get("selected_row_number")
        if selected_rows:
            rows = [row for row in rows if (row["sheet"], row["row_number"]) in selected_rows]
        elif selected_sheet and selected_row_number is not None:
            rows = [row for row in rows if row["sheet"] == selected_sheet and row["row_number"] == int(selected_row_number)]
        if not rows:
            raise ValueError("No se encontraron filas con Programa/Nivel y URL usando las columnas seleccionadas.")
        workflow_mode = rows[0].get("workflow_mode", "product_release")
        job["workflow_mode"] = workflow_mode
        base_config = dict(raw_config)
        base_config.update({
            "utel_url": rows[0]["utel_url"],
            "program_name": rows[0]["program_name"],
            "dry_run": raw_config.get("dry_run", True),
            "workflow_mode": workflow_mode,
            "source_filename": filename,
        })
        verification_queue = []
        job["phase"] = "UTEL: enviando formularios"
        for index, row in enumerate(rows, 1):
            row_config = dict(base_config)
            if row.get("workflow_mode") == "form_validation" and not row.get("country"):
                raise ValueError(
                    f"La fila {row['row_number']} no tiene pais en la columna Locale/Country."
                )
            row_country = (
                row["country"]
                if row.get("workflow_mode") == "form_validation"
                else row["country"] or raw_config.get("country", "Ecuador")
            )
            row_country = service.effective_country(row_country, row["level"], row["utel_url"])
            navigation = (
                service.deploy_navigation_plan(row["level"], row_country)
                if row.get("workflow_mode") == "form_validation"
                else {
                    "modality": row.get("modality") or raw_config.get("modality", "En linea"),
                    "level": row["level"] or raw_config.get("level", "Licenciatura"),
                    "navigation_modality": "",
                    "navigation_level": "",
                    "navigation_sublevel": "",
                }
            )
            row_config.update({
                "utel_url": row["utel_url"],
                "program_name": row["program_name"],
                "program_selection_strategy": "exact_match" if row["program_name"] else "first",
                "modality": navigation["modality"],
                "level": navigation["level"],
                "navigation_modality": navigation["navigation_modality"],
                "navigation_level": navigation["navigation_level"],
                "navigation_sublevel": navigation["navigation_sublevel"],
                "country": row_country,
                "form_type": row["form_type"] or raw_config.get("form_type", "lateral"),
                # El país de esta fila manda: nunca heredar el CRM de otra fila.
                "inconcert_url": service.default_inconcert_url(row_country) or row["inconcert_url"],
                "workflow_mode": row.get("workflow_mode", "product_release"),
                "name": f"{raw_config.get('name', 'QA UTEL')} - {row.get('test_case') or row['program_name'] or row['level']}",
            })
            config = UtelQaConfig.model_validate(row_config)
            lead = TestLeadService(settings.database_path).reserve(config.country)
            config = config.model_copy(update={"lead": config.lead.model_copy(update=lead)})
            if not config.dry_run:
                config = config.model_copy(update={"defer_crm_verification": True})
            job.update({
                "current_program": row.get("test_case") or row["program_name"] or row["level"],
                "current_row": row["row_number"],
                "current_lead_name": config.lead.name,
                "current_lead_email": config.lead.email,
                "current_lead_phone": config.lead.phone,
                "last_error": "",
            })
            result = await UtelInconcertRunner(settings).run(config)
            serializable_result = {**result, "stages": [stage.model_dump() for stage in result["stages"]]}
            results.append({"row": row, "result": serializable_result})
            # El reporte se actualiza fila por fila para no perder los enlaces
            # ya obtenidos si el backend se reinicia o el lote se detiene.
            _save_utel_batch_report(settings, job_id, filename, content, mapping, results)
            job["download_url"] = f"/api/bots/utel-inconcert/batch/{job_id}/download"
            if serializable_result["status"] == "PASS" and not config.dry_run:
                verification_queue.append((len(results) - 1, config))
            failed_stage = next((stage for stage in serializable_result["stages"] if stage["status"] == "FAIL"), None)
            job.update({
                "completed": index,
                "success": sum(1 for item in results if item["result"]["status"] == "PASS"),
                "failed": sum(1 for item in results if item["result"]["status"] == "FAIL"),
                "current_program": row.get("test_case") or row["program_name"] or row["level"],
                "current_row": row["row_number"],
                "last_error": failed_stage["message"] if failed_stage else "",
                "results": results,
            })
            if index < len(rows) and inter_row_delay > 0:
                await asyncio.sleep(inter_row_delay)

        if verification_queue:
            job["phase"] = "CRM: verificando leads por país"
            logger.info(
                "Lote %s con pausa entre verificaciones CRM: %ss",
                job_id,
                inter_row_delay,
            )
            for verification_index, (result_index, submitted_config) in enumerate(
                sorted(verification_queue, key=lambda item: item[1].country.casefold()),
                1,
            ):
                verify_config = submitted_config.model_copy(
                    update={"defer_crm_verification": False, "verification_only": True}
                )
                job.update({
                    "current_program": results[result_index]["row"].get("test_case") or results[result_index]["row"]["program_name"] or results[result_index]["row"]["level"],
                    "current_row": results[result_index]["row"]["row_number"],
                    "current_lead_name": verify_config.lead.name,
                    "current_lead_email": verify_config.lead.email,
                    "current_lead_phone": verify_config.lead.phone,
                    "last_error": "",
                })
                verification = await UtelInconcertRunner(settings).run(verify_config)
                serializable_verification = {**verification, "stages": [stage.model_dump() for stage in verification["stages"]]}
                submission = results[result_index]["result"]
                results[result_index]["result"] = {
                    **serializable_verification,
                    "selected_program_name": submission.get("selected_program_name"),
                    "stages": [*submission["stages"], *serializable_verification["stages"]],
                }
                # Sustituye el checkpoint con el enlace CRM confirmado.
                _save_utel_batch_report(settings, job_id, filename, content, mapping, results)
                job.update({
                    "completed": len(rows),
                    "success": sum(1 for item in results if item["result"]["status"] == "PASS"),
                    "failed": sum(1 for item in results if item["result"]["status"] == "FAIL"),
                    "results": results,
                })
                if verification_index < len(verification_queue) and inter_row_delay > 0:
                    await asyncio.sleep(inter_row_delay)

        _save_utel_batch_report(settings, job_id, filename, content, mapping, results)
        job.update({"status": "PASS", "finished_at": datetime.now().isoformat(timespec="seconds"), "download_url": f"/api/bots/utel-inconcert/batch/{job_id}/download", "results": results})
    except asyncio.CancelledError:
        _save_utel_batch_report(settings, job_id, filename, content, mapping, results)
        job.update({"status": "CANCELLED", "finished_at": datetime.now().isoformat(timespec="seconds"), "summary": "Lote cancelado durante la ejecución."})
        raise
    except Exception as error:  # noqa: BLE001
        logger.exception("No se pudo completar el lote UTEL/InConcert %s", job_id)
        _save_utel_batch_report(settings, job_id, filename, content, mapping, results)
        job.update({"status": "FAIL", "finished_at": datetime.now().isoformat(timespec="seconds"), "summary": str(error)})


@router.post("/bots/utel-inconcert/batch-run", status_code=202)
async def run_utel_batch(request: Request, file: UploadFile = File(...), config: str = Form(...), mapping: str = Form(...)) -> dict:
    """Inicia la ejecución de todas las filas del Excel con un mapeo elegido."""

    if not (file.filename or "").lower().endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="Comparte un archivo Excel con extensión .xlsx.")
    try:
        raw_config = json.loads(config)
        selected_mapping = json.loads(mapping)
        if not (selected_mapping.get("program_name") or selected_mapping.get("level")) or not selected_mapping.get("utel_url"):
            raise ValueError("Selecciona una columna de Programa o Nivel, además de la columna URL.")
        content = await file.read()
        preview_rows = BotSpreadsheetService().rows_for_mapping(content, selected_mapping)
        selected_rows = {
            (str(item.get("sheet")), int(item.get("row_number")))
            for item in selected_mapping.get("selected_rows", [])
            if item.get("sheet") and item.get("row_number") is not None
        }
        selected_sheet = selected_mapping.get("selected_sheet")
        selected_row_number = selected_mapping.get("selected_row_number")
        if selected_rows:
            preview_rows = [row for row in preview_rows if (row["sheet"], row["row_number"]) in selected_rows]
        elif selected_sheet and selected_row_number is not None:
            preview_rows = [row for row in preview_rows if row["sheet"] == selected_sheet and row["row_number"] == int(selected_row_number)]
        if not preview_rows:
            raise ValueError("No se encontraron filas válidas con el mapeo seleccionado.")
    except (ValueError, json.JSONDecodeError) as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    job_id = uuid4().hex
    request.app.state.utel_batch_jobs[job_id] = {
        "job_id": job_id,
        "status": "RUNNING",
        "total": len(preview_rows),
        "completed": 0,
        "success": 0,
        "failed": 0,
        "phase": "UTEL: preparando envíos",
        "download_url": None,
        "workflow_mode": preview_rows[0].get("workflow_mode", "product_release"),
        "dry_run": raw_config.get("dry_run", True),
    }
    task = asyncio.create_task(_run_utel_batch_job(request.app, job_id, content, file.filename or "resultado.xlsx", raw_config, selected_mapping))
    request.app.state.bot_tasks[job_id] = task
    task.add_done_callback(lambda _: request.app.state.bot_tasks.pop(job_id, None))
    return request.app.state.utel_batch_jobs[job_id]


@router.get("/bots/utel-inconcert/batch/{job_id}")
async def utel_batch_status(request: Request, job_id: str) -> dict:
    job = request.app.state.utel_batch_jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="El lote no existe o ya no está disponible.")
    return job


@router.post("/bots/utel-inconcert/batch/{job_id}/cancel")
async def cancel_utel_batch(request: Request, job_id: str) -> dict:
    job = request.app.state.utel_batch_jobs.get(job_id)
    task = request.app.state.bot_tasks.get(job_id)
    if job is None or task is None or task.done():
        raise HTTPException(status_code=404, detail="El lote ya terminó o no existe.")
    job.update({"status": "CANCELLED", "finished_at": datetime.now().isoformat(timespec="seconds"), "summary": "Lote detenido por el usuario."})
    task.cancel()
    return job


@router.get("/bots/utel-inconcert/batch/{job_id}/download")
async def download_utel_batch(request: Request, job_id: str) -> FileResponse:
    output_dir = request.app.state.settings.storage_dir / "reports" / "bot"
    path = next(output_dir.glob(f"{job_id}_*.xlsx"), None)
    if path is None or not path.is_file():
        raise HTTPException(status_code=404, detail="El Excel todavía no está disponible.")
    return FileResponse(path, filename=path.name, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


@router.post("/weekly-auto/run", response_model=WeeklyAutoJobResponse, status_code=202)
async def run_weekly_auto(request: Request, config: WeeklyAutoConfig) -> dict:
    """Inicia la captura semanal sin bloquear la interfaz."""

    if not config.urls and not config.use_default_urls:
        raise HTTPException(status_code=400, detail="Debes indicar URLs o activar el uso de URLs por defecto.")
    job_id = uuid4().hex
    started_at = datetime.now().isoformat(timespec="seconds")
    request.app.state.weekly_auto_jobs[job_id] = {
        "job_id": job_id,
        "name": config.name,
        "status": "RUNNING",
        "started_at": started_at,
        "finished_at": None,
        "duration_seconds": None,
        "total_urls": None,
        "completed": 0,
        "successful": 0,
        "failed": 0,
        "skipped": 0,
        "current_url": None,
        "current_index": None,
        "summary": "Weekly Auto ejecutándose en segundo plano.",
        "result": None,
    }
    task = asyncio.create_task(_run_weekly_auto_job(request.app, job_id, config))
    request.app.state.bot_tasks[job_id] = task
    task.add_done_callback(lambda _: request.app.state.bot_tasks.pop(job_id, None))
    return request.app.state.weekly_auto_jobs[job_id]


@router.get("/weekly-auto/runs/{job_id}", response_model=WeeklyAutoJobResponse)
async def weekly_auto_status(request: Request, job_id: str) -> dict:
    """Consulta el estado de la corrida semanal."""

    job = request.app.state.weekly_auto_jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="La corrida semanal no existe o ya no está disponible.")
    return job


@router.post("/weekly-auto/runs/{job_id}/cancel")
async def cancel_weekly_auto_run(request: Request, job_id: str) -> dict:
    """Cancela una corrida semanal en curso."""

    job = request.app.state.weekly_auto_jobs.get(job_id)
    task = request.app.state.bot_tasks.get(job_id)
    if job is None or task is None or task.done():
        raise HTTPException(status_code=404, detail="La corrida ya terminó o no existe.")
    job.update({"status": "CANCELLED", "finished_at": datetime.now().isoformat(timespec="seconds"), "summary": "Corrida cancelada por el usuario."})
    task.cancel()
    return job

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


async def _run_bot_job(application, job_id: str, config: BotConfig) -> None:
    """Ejecuta el bot fuera de la solicitud HTTP y actualiza su estado."""

    settings = application.state.settings
    try:
        logger.info("Iniciando bot en segundo plano: %s (%s)", config.name, job_id)
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
        application.state.bot_jobs[job_id] = {
            "job_id": job_id,
            "name": config.name,
            "status": result["status"],
            "started_at": result["started_at"],
            "finished_at": result["finished_at"],
            "duration_seconds": result["duration_seconds"],
            "summary": result["summary"],
            "result": serializable_result,
        }
        logger.info("Bot finalizado: %s - %s", config.name, result["status"])
    except asyncio.CancelledError:
        logger.info("Bot cancelado durante el cierre del backend: %s (%s)", config.name, job_id)
        raise
    except Exception as error:  # noqa: BLE001 - el estado se devuelve a la interfaz
        logger.exception("No se pudo completar el bot %s", config.name)
        now = datetime.now().isoformat(timespec="seconds")
        application.state.bot_jobs[job_id] = {
            "job_id": job_id,
            "name": config.name,
            "status": "FAIL",
            "started_at": application.state.bot_jobs[job_id]["started_at"],
            "finished_at": now,
            "duration_seconds": None,
            "summary": str(error),
            "result": None,
        }


@router.post("/bots/run", response_model=BotStartResponse, status_code=202)
async def run_bot(request: Request, config: BotConfig) -> dict:
    """Inicia un flujo en segundo plano y devuelve el control inmediatamente."""

    job_id = uuid4().hex
    started_at = datetime.now().isoformat(timespec="seconds")
    request.app.state.bot_jobs[job_id] = {
        "job_id": job_id,
        "name": config.name,
        "status": "RUNNING",
        "started_at": started_at,
        "finished_at": None,
        "duration_seconds": None,
        "summary": "El bot está ejecutándose en segundo plano.",
        "result": None,
    }
    task = asyncio.create_task(_run_bot_job(request.app, job_id, config))
    request.app.state.bot_tasks[job_id] = task
    task.add_done_callback(lambda _: request.app.state.bot_tasks.pop(job_id, None))
    return {"job_id": job_id, "name": config.name, "status": "RUNNING", "started_at": started_at}


@router.get("/bots/runs/{job_id}", response_model=BotJobResponse)
async def bot_run_status(request: Request, job_id: str) -> dict:
    """Consulta el progreso o resultado de un bot en segundo plano."""

    job = request.app.state.bot_jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="La ejecución del bot no existe o ya no está disponible.")
    return job


async def _run_utel_inconcert_job(application, job_id: str, config: UtelQaConfig) -> None:
    """Ejecuta el flujo especializado UTEL/InConcert en segundo plano."""

    settings = application.state.settings
    try:
        logger.info("Iniciando flujo UTEL/InConcert: %s (%s)", config.name, job_id)
        result = await UtelInconcertRunner(settings).run(config)
        serializable_result = {
            **result,
            "stages": [stage.model_dump() for stage in result["stages"]],
        }
        ExecutionRepository(settings.database_path).create_execution(
            {
                "automation_type": "utel_inconcert_qa",
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
        application.state.utel_inconcert_jobs[job_id] = {
            "job_id": job_id,
            "name": config.name,
            "status": result["status"],
            "started_at": result["started_at"],
            "finished_at": result["finished_at"],
            "duration_seconds": result["duration_seconds"],
            "summary": result["summary"],
            "result": serializable_result,
        }
        logger.info("Flujo UTEL/InConcert finalizado: %s - %s", config.name, result["status"])
    except asyncio.CancelledError:
        logger.info("Flujo UTEL/InConcert cancelado durante el cierre: %s (%s)", config.name, job_id)
        raise
    except Exception as error:  # noqa: BLE001 - el estado se devuelve a la interfaz
        logger.exception("No se pudo completar el flujo UTEL/InConcert %s", config.name)
        now = datetime.now().isoformat(timespec="seconds")
        application.state.utel_inconcert_jobs[job_id] = {
            "job_id": job_id,
            "name": config.name,
            "status": "FAIL",
            "started_at": application.state.utel_inconcert_jobs[job_id]["started_at"],
            "finished_at": now,
            "duration_seconds": None,
            "summary": str(error),
            "result": None,
        }


async def _run_weekly_auto_job(application, job_id: str, config: WeeklyAutoConfig) -> None:
    """Ejecuta la corrida semanal en background y actualiza el estado."""

    settings = application.state.settings
    try:
        logger.info("Iniciando Weekly Auto: %s (%s)", config.name, job_id)
        def progress(payload: dict[str, Any]) -> None:
            job = application.state.weekly_auto_jobs.get(job_id)
            if not job:
                return
            job.update(
                {
                    "current_index": payload["index"],
                    "total_urls": payload["total"],
                    "current_url": payload["url"],
                    "completed": payload["index"] - (1 if payload["status"] == "SKIPPED" else 0),
                    "successful": job.get("successful", 0) + (1 if payload["status"] == "PASS" else 0),
                    "failed": job.get("failed", 0) + (1 if payload["status"] == "FAIL" else 0),
                    "skipped": job.get("skipped", 0) + (1 if payload["status"] == "SKIPPED" else 0),
                    "summary": f"Proceso {payload['index']}/{payload['total']}: {payload['status']} - {payload['url']}",
                }
            )

        result = await WeeklyAutoRunner(settings).run(config, progress_callback=progress)
        serializable_result = result
        logger.info("Weekly Auto finalizado: %s", config.name)

        ExecutionRepository(settings.database_path).create_execution(
            {
                "automation_type": "weekly_auto",
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
        application.state.weekly_auto_jobs[job_id] = {
            "job_id": job_id,
            "name": config.name,
            "status": result["status"],
            "started_at": result["started_at"],
            "finished_at": result["finished_at"],
            "duration_seconds": result["duration_seconds"],
            "total_urls": result["total_urls"],
            "completed": result["completed"],
            "successful": result["successful"],
            "failed": result["failed"],
            "skipped": result["skipped"],
            "current_url": None,
            "current_index": None,
            "summary": result["summary"],
            "result": serializable_result,
        }
        logger.info("Weekly Auto finalizado: %s - %s", config.name, result["status"])
    except asyncio.CancelledError:
        logger.info("Weekly Auto cancelado durante ejecución: %s (%s)", config.name, job_id)
        application.state.weekly_auto_jobs[job_id] = {
            "job_id": job_id,
            "name": config.name,
            "status": "CANCELLED",
            "started_at": application.state.weekly_auto_jobs[job_id]["started_at"],
            "finished_at": datetime.now().isoformat(timespec="seconds"),
            "duration_seconds": None,
            "total_urls": None,
            "completed": 0,
            "successful": 0,
            "failed": 0,
            "skipped": 0,
            "current_url": None,
            "current_index": None,
            "summary": "Corrida cancelada por el usuario.",
            "result": None,
        }
        return
    except Exception as error:  # noqa: BLE001 - se regresa a la UI en forma de estado
        logger.exception("No se pudo completar Weekly Auto %s", config.name)
        now = datetime.now().isoformat(timespec="seconds")
        application.state.weekly_auto_jobs[job_id] = {
            "job_id": job_id,
            "name": config.name,
            "status": "FAIL",
            "started_at": application.state.weekly_auto_jobs[job_id]["started_at"],
            "finished_at": now,
            "duration_seconds": None,
            "total_urls": None,
            "completed": 0,
            "successful": 0,
            "failed": 0,
            "skipped": 0,
            "current_url": None,
            "current_index": None,
            "summary": str(error),
            "result": None,
        }


@router.post("/bots/utel-inconcert/run", response_model=BotStartResponse, status_code=202)
async def run_utel_inconcert_bot(request: Request, config: UtelQaConfig) -> dict:
    """Inicia el flujo UTEL/InConcert sin bloquear la interfaz."""

    country_crm = BotSpreadsheetService.default_inconcert_url(config.country)
    if country_crm:
        config = config.model_copy(update={"inconcert_url": country_crm})
    generated_lead = TestLeadService(request.app.state.settings.database_path).reserve(config.country)
    config = config.model_copy(
        update={
            "lead": config.lead.model_copy(
                update={
                    "name": generated_lead["name"],
                    "email": generated_lead["email"],
                    "phone": generated_lead["phone"],
                }
            )
        }
    )
    job_id = uuid4().hex
    started_at = datetime.now().isoformat(timespec="seconds")
    request.app.state.utel_inconcert_jobs[job_id] = {
        "job_id": job_id,
        "name": config.name,
        "status": "RUNNING",
        "started_at": started_at,
        "finished_at": None,
        "duration_seconds": None,
        "summary": "El flujo UTEL/InConcert esta ejecutandose en segundo plano.",
        "result": None,
    }
    task = asyncio.create_task(_run_utel_inconcert_job(request.app, job_id, config))
    request.app.state.bot_tasks[job_id] = task
    task.add_done_callback(lambda _: request.app.state.bot_tasks.pop(job_id, None))
    return {
        "job_id": job_id,
        "name": config.name,
        "status": "RUNNING",
        "started_at": started_at,
        "lead_email": generated_lead["email"],
        "lead_phone": generated_lead["phone"],
        "lead_name": generated_lead["name"],
    }


@router.get("/bots/utel-inconcert/runs/{job_id}", response_model=UtelQaJobResponse)
async def utel_inconcert_status(request: Request, job_id: str) -> dict:
    """Consulta el progreso o resultado del flujo UTEL/InConcert."""

    job = request.app.state.utel_inconcert_jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="La ejecucion UTEL/InConcert no existe o ya no esta disponible.")
    return job


@router.post("/bots/utel-inconcert/runs/{job_id}/cancel")
async def cancel_utel_run(request: Request, job_id: str) -> dict:
    job = request.app.state.utel_inconcert_jobs.get(job_id)
    task = request.app.state.bot_tasks.get(job_id)
    if job is None or task is None or task.done():
        raise HTTPException(status_code=404, detail="La ejecución ya terminó o no existe.")
    job.update({"status": "CANCELLED", "finished_at": datetime.now().isoformat(timespec="seconds"), "summary": "Ejecución detenida por el usuario."})
    task.cancel()
    return job


@router.post("/pdp/validate")
async def validate_pdp(
    request: Request,
    excel_file: UploadFile = File(...),
    docx_file: UploadFile = File(...),
) -> dict:
    """Compara información de PDP en Excel/DOCX contra sus páginas web."""

    if not (excel_file.filename or "").lower().endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="Comparte un archivo Excel con extensión .xlsx.")
    if not (docx_file.filename or "").lower().endswith(".docx"):
        raise HTTPException(status_code=400, detail="Comparte un documento Word con extensión .docx.")

    settings = request.app.state.settings
    try:
        result = await PdpValidationService(settings).validate(
            await excel_file.read(),
            await docx_file.read(),
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
