"""API independiente para simular y aplicar sincronizaciones de hreflangs."""

from __future__ import annotations

import asyncio
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from ..config.settings import Settings
from ..modules.strapi_hreflangs.countries import LOCALES
from ..modules.strapi_hreflangs.report import build_report
from ..modules.strapi_hreflangs.sync import HreflangSynchronizer
from ..services.strapi_client import StrapiClient


router = APIRouter(prefix="/api/strapi/hreflangs", tags=["strapi-hreflangs"])


class HreflangRunRequest(BaseModel):
    """Valida las opciones para un trabajo de simulación o escritura explícita."""

    locale: str
    max_products: int | None = Field(default=None, ge=1, le=100000)
    apply: bool = False
    confirmation: str = ""
    expected_host: str = ""
    preview_job_id: str = ""


def _token(settings: Settings) -> str:
    """Obtiene el secreto de Strapi sin incluirlo en respuestas o registros."""

    value = settings.strapi_token
    return value.get_secret_value() if hasattr(value, "get_secret_value") else str(value)


def _host(settings: Settings) -> str:
    """Devuelve únicamente el hostname configurado para validarlo en el UI."""

    return (urlparse(settings.strapi_url).hostname or "").lower()


def _ensure_configuration(settings: Settings) -> None:
    """Evita iniciar procesos si la configuración o el host no son válidos."""

    parsed = urlparse(settings.strapi_url)
    if parsed.scheme != "https" or not parsed.hostname or not parsed.hostname.endswith(".utel.edu.mx"):
        raise HTTPException(status_code=503, detail="Configura STRAPI_URL con un endpoint HTTPS de UTEL antes de usar este módulo.")
    if not _token(settings):
        raise HTTPException(status_code=503, detail="Falta STRAPI_TOKEN en la configuración del backend.")


@router.get("/config")
async def hreflang_config(request: Request) -> dict:
    """Entrega configuración no sensible necesaria para confirmar la ejecución."""

    settings: Settings = request.app.state.settings
    return {
        "configured": bool(_token(settings) and _host(settings).endswith(".utel.edu.mx") and urlparse(settings.strapi_url).scheme == "https"),
        "host": _host(settings),
        "endpoint": settings.strapi_product_endpoint,
        "href_langs_path": settings.strapi_hreflangs_path,
        "locales": list(LOCALES),
    }


@router.post("/run", status_code=202)
async def run_hreflang_job(payload: HreflangRunRequest, request: Request) -> dict:
    """Crea un job aislado; las escrituras exigen confirmar el hostname exacto."""

    settings: Settings = request.app.state.settings
    _ensure_configuration(settings)
    if payload.locale not in LOCALES:
        raise HTTPException(status_code=400, detail="El locale seleccionado no está disponible.")
    host = _host(settings)
    if not settings.strapi_hreflangs_path or "." not in settings.strapi_hreflangs_path:
        raise HTTPException(status_code=503, detail="STRAPI_HREFLANGS_PATH debe identificar un campo anidado; no se permite reemplazar el componente completo.")
    if payload.apply and (payload.expected_host.lower() != host or payload.confirmation != f"APLICAR {host}"):
        raise HTTPException(status_code=400, detail=f"Para escribir, confirma el host escribiendo: APLICAR {host}")
    if payload.apply:
        preview = request.app.state.strapi_hreflang_jobs.get(payload.preview_job_id)
        if (
            not preview
            or preview.get("mode") != "dry-run"
            or preview.get("status") not in {"SUCCESS", "WARNING"}
            or preview.get("locale") != payload.locale
            or preview.get("max_products") != payload.max_products
            or preview.get("host") != host
            or preview.get("consumed_by")
            or not any(item.get("action") == "would-update" for item in preview.get("results", []))
        ):
            raise HTTPException(status_code=409, detail="Ejecuta una simulación con los mismos parámetros antes de aplicar.")

    job_id = uuid4().hex
    job = {
        "job_id": job_id,
        "status": "RUNNING",
        "mode": "apply" if payload.apply else "dry-run",
        "locale": payload.locale,
        "max_products": payload.max_products,
        "host": host,
        "total": 0,
        "completed": 0,
        "progress": [],
        "started_at": datetime.now(timezone.utc).isoformat(),
    }
    request.app.state.strapi_hreflang_jobs[job_id] = job
    if payload.apply:
        request.app.state.strapi_hreflang_jobs[payload.preview_job_id]["consumed_by"] = job_id
    request.app.state.bot_tasks[f"hreflang-{job_id}"] = asyncio.create_task(_run_job(request.app, job_id, payload))
    return {key: value for key, value in job.items() if key != "progress"} | {"download_url": None}


async def _run_job(application, job_id: str, payload: HreflangRunRequest) -> None:
    """Ejecuta el lote, guarda el Excel y conserva progreso por producto."""

    settings: Settings = application.state.settings
    job = application.state.strapi_hreflang_jobs[job_id]
    client = None
    synchronizer = None
    try:
        client = StrapiClient(
            settings.strapi_url,
            _token(settings),
            settings.strapi_product_endpoint,
            settings.strapi_timeout_seconds,
        )
        synchronizer = HreflangSynchronizer(
            client,
            href_langs_path=settings.strapi_hreflangs_path,
            timeout=settings.strapi_timeout_seconds,
        )

        def record(message: str) -> None:
            """Agrega mensajes acotados de progreso para el panel del módulo."""

            job["progress"].append(message)
            job["progress"] = job["progress"][-300:]
            source_count = re.match(r"^Fuente lista: (\d+) productos", message)
            product_progress = re.match(r"^(\d+)/(\d+) · ", message)
            if source_count:
                job["total"] = int(source_count.group(1))
            elif product_progress:
                job["completed"] = int(product_progress.group(1))
                job["total"] = int(product_progress.group(2))

        results = await synchronizer.run(
            payload.locale,
            apply=payload.apply,
            max_products=payload.max_products,
            page_size=100,
            progress=record,
        )
        job["total"] = len(results)
        job["completed"] = len(results)
        report_dir = settings.storage_dir / "reports" / "strapi-hreflangs"
        report_dir.mkdir(parents=True, exist_ok=True)
        report_path = report_dir / f"{job_id}_{payload.locale}_{job['mode']}.xlsx"
        report_path.write_bytes(build_report(results, payload.apply))
        counts = {}
        for result in results:
            counts[result["action"]] = counts.get(result["action"], 0) + 1
        job.update({
            "status": "WARNING" if counts.get("error") else "SUCCESS",
            "results": results,
            "summary": counts,
            "report_path": str(report_path),
            "download_url": f"/api/strapi/hreflangs/jobs/{job_id}/download",
            "finished_at": datetime.now(timezone.utc).isoformat(),
        })
    except Exception as error:  # noqa: BLE001 - una falla queda registrada en el job.
        job.update({"status": "FAILED", "message": str(error), "finished_at": datetime.now(timezone.utc).isoformat()})
    finally:
        if synchronizer:
            await synchronizer.close()
        if client:
            await client.close()


@router.get("/jobs/{job_id}")
async def hreflang_job_status(request: Request, job_id: str, after: int = 0) -> dict:
    """Expone estado y progreso sin devolver secretos de conexión."""

    job = request.app.state.strapi_hreflang_jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job de hreflangs no encontrado.")
    return {**job, "progress": job.get("progress", [])[max(0, after):], "progress_offset": len(job.get("progress", []))}


@router.get("/jobs/{job_id}/download")
async def download_hreflang_report(request: Request, job_id: str) -> FileResponse:
    """Descarga el reporte Excel cuando la ejecución ya lo generó."""

    job = request.app.state.strapi_hreflang_jobs.get(job_id)
    report_path = Path(job["report_path"]) if job and job.get("report_path") else None
    if not report_path or not report_path.is_file():
        raise HTTPException(status_code=404, detail="El reporte aún no está disponible.")
    return FileResponse(
        report_path,
        filename=report_path.name,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
