from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse

from ..config.settings import Settings
from ..modules.strapi_products.description_runner import StrapiDescriptionRunner
from ..modules.strapi_products.fichas import FichasLookup
from ..modules.strapi_products.balancer_catalog import BalancerProgramCatalog
from ..modules.strapi_products.report import build_description_report, build_report
from ..modules.strapi_products.country import COUNTRIES, detect_country_from_filename
from ..modules.strapi_products.schema_validation import product_schema_version
from ..modules.strapi_products.runner import StrapiProductRunner
from ..modules.strapi_products.spreadsheet import read_product_rows
from ..services.strapi_client import StrapiClient
from ..services.google_drive_client import GoogleDriveClient


router = APIRouter(prefix="/api/strapi/products", tags=["strapi-products"])

DEFAULT_COUNTRIES = {
    item.label.casefold().replace(" ", "-"): {"label": item.label, "locale": item.locale, "slug": item.slug, "code": item.code}
    for item in COUNTRIES.values()
}


def _countries(settings: Settings) -> dict[str, dict[str, str]]:
    try:
        configured = json.loads(settings.strapi_countries_json)
        if isinstance(configured, dict) and configured:
            return configured
    except (TypeError, json.JSONDecodeError):
        pass
    return DEFAULT_COUNTRIES


def _token(settings: Settings) -> str:
    value = settings.strapi_token
    return value.get_secret_value() if hasattr(value, "get_secret_value") else str(value)


@router.get("/countries")
async def strapi_product_countries(request: Request) -> dict:
    return {"countries": _countries(request.app.state.settings)}


@router.post("/preview")
async def preview_strapi_product_file(file: UploadFile = File(...)) -> dict:
    if not (file.filename or "").lower().endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="Selecciona un archivo .xlsx.")
    try:
        rows = read_product_rows(await file.read())
        return {"filename": file.filename, "total": len(rows), "rows": [row.__dict__ for row in rows[:100]]}
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.post("/run", status_code=202)
async def run_strapi_product_job(request: Request, file: UploadFile = File(...), country: str = Form(""), dry_run: str = Form("true")) -> dict:
    settings: Settings = request.app.state.settings
    if not (file.filename or "").lower().endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="Selecciona un archivo .xlsx.")
    if dry_run.casefold() not in {"true", "false"}:
        raise HTTPException(status_code=400, detail="dry_run debe ser true o false.")
    try:
        detected = detect_country_from_filename(file.filename or "")
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    country_config = {"label": detected.label, "locale": detected.locale, "slug": detected.slug, "code": detected.code}
    if not settings.strapi_url or not _token(settings):
        raise HTTPException(status_code=500, detail="Faltan STRAPI_URL o STRAPI_TOKEN en la configuracion del backend.")

    content = await file.read()
    job_id = uuid4().hex
    request.app.state.strapi_product_jobs[job_id] = {
        "job_id": job_id, "status": "RUNNING", "country": detected.label, "country_code": detected.code, "locale": detected.locale, "dry_run": dry_run.casefold() == "true",
        "filename": file.filename, "started_at": datetime.now(timezone.utc).isoformat(), "completed": 0,
    }
    request.app.state.bot_tasks[job_id] = asyncio.create_task(_run_job(request.app, job_id, content, file.filename or "resultado.xlsx", country_config))
    return request.app.state.strapi_product_jobs[job_id]


@router.post("/descriptions/run", status_code=202)
async def run_strapi_description_job(request: Request, file: UploadFile = File(...), fichas_file: UploadFile | None = File(None), schema_file: UploadFile | None = File(None), dry_run: str = Form("true")) -> dict:
    settings: Settings = request.app.state.settings
    if not (file.filename or "").lower().endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="Selecciona un archivo .xlsx.")
    if fichas_file and not (fichas_file.filename or "").lower().endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="El archivo de fichas debe ser .xlsx.")
    product_schema = None
    if schema_file:
        if not (schema_file.filename or "").lower().endswith(".json"):
            raise HTTPException(status_code=400, detail="El esquema de Strapi debe ser un archivo .json.")
        schema_content = await schema_file.read()
        if len(schema_content) > 5 * 1024 * 1024:
            raise HTTPException(status_code=413, detail="El esquema JSON supera el límite de 5 MB.")
        try:
            product_schema = json.loads(schema_content)
        except (json.JSONDecodeError, UnicodeDecodeError) as error:
            raise HTTPException(status_code=400, detail="El archivo de esquema no contiene JSON válido.") from error
        product_definition = product_schema.get("product", {}) if isinstance(product_schema, dict) else {}
        components = product_schema.get("components") if isinstance(product_schema, dict) else None
        valid_components = isinstance(components, dict) and all(
            isinstance(component, dict) and isinstance(component.get("attributes"), dict)
            for component in components.values()
        )
        if not isinstance(product_definition, dict) or product_definition.get("uid") != "api::product.product" or not isinstance(product_definition.get("attributes"), dict) or not valid_components:
            raise HTTPException(status_code=400, detail="El JSON no tiene el formato de esquema de producto Strapi esperado.")
    if dry_run.casefold() not in {"true", "false"}:
        raise HTTPException(status_code=400, detail="dry_run debe ser true o false.")
    try:
        detected = detect_country_from_filename(file.filename or "")
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    if not settings.strapi_url or not _token(settings):
        raise HTTPException(status_code=500, detail="Faltan STRAPI_URL o STRAPI_TOKEN en la configuracion del backend.")

    job_id = uuid4().hex
    content = await file.read()
    fichas_content = await fichas_file.read() if fichas_file else None
    request.app.state.strapi_product_jobs[job_id] = {
        "job_id": job_id, "operation": "descriptions", "status": "RUNNING", "country": detected.label, "country_code": detected.code, "locale": detected.locale,
        "dry_run": dry_run.casefold() == "true", "filename": file.filename, "schema_version": product_schema_version(product_schema), "schema_source": "json" if product_schema else "integrado", "started_at": datetime.now(timezone.utc).isoformat(), "completed": 0,
    }
    request.app.state.bot_tasks[job_id] = asyncio.create_task(_run_description_job(request.app, job_id, content, file.filename or "resultado.xlsx", detected, fichas_content, product_schema))
    return request.app.state.strapi_product_jobs[job_id]


@router.get("/jobs/{job_id}")
async def strapi_product_job_status(request: Request, job_id: str) -> dict:
    job = request.app.state.strapi_product_jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job no encontrado.")
    return job


@router.get("/jobs/{job_id}/download")
async def download_strapi_product_report(request: Request, job_id: str) -> FileResponse:
    job = request.app.state.strapi_product_jobs.get(job_id)
    if not job or not job.get("report_path"):
        raise HTTPException(status_code=404, detail="El reporte aun no esta disponible.")
    return FileResponse(job["report_path"], filename=Path(job["report_path"]).name, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


async def _run_job(application, job_id: str, content: bytes, filename: str, country_config: dict[str, str]) -> None:
    settings: Settings = application.state.settings
    job = application.state.strapi_product_jobs[job_id]
    client = None
    try:
        rows = read_product_rows(content)
        slug_map = {key: value["slug"] for key, value in _countries(settings).items() if value.get("slug")}
        slug_map.update({item.label.casefold(): item.slug for item in COUNTRIES.values()})
        client = StrapiClient(settings.strapi_url, _token(settings), settings.strapi_product_endpoint, settings.strapi_timeout_seconds)
        runner = StrapiProductRunner(client, country_config["label"], country_config["locale"], slug_map, dry_run=job["dry_run"], expected_host=settings.strapi_expected_host, title_field=settings.strapi_program_field, seo_field=settings.strapi_seo_field, canonical_field=settings.strapi_canonical_field, status=settings.strapi_content_status)
        results, summary = await runner.run(rows)
        report_dir = settings.storage_dir / "reports" / "strapi"
        report_dir.mkdir(parents=True, exist_ok=True)
        report_path = report_dir / f"{job_id}_{Path(filename).stem}.xlsx"
        report_path.write_bytes(build_report(results, summary))
        job.update({"status": "SUCCESS" if not summary.failed and not summary.invalid_data else "WARNING", "completed": summary.total, "summary": summary.as_dict(), "results": [result.as_dict() for result in results], "report_path": str(report_path), "download_url": f"/api/strapi/products/jobs/{job_id}/download", "finished_at": datetime.now(timezone.utc).isoformat()})
    except Exception as error:  # noqa: BLE001
        job.update({"status": "FAILED", "message": str(error), "finished_at": datetime.now(timezone.utc).isoformat()})
    finally:
        if client:
            await client.close()


async def _run_description_job(application, job_id: str, content: bytes, filename: str, country_config, fichas_content: bytes | None = None, product_schema: dict | None = None) -> None:
    settings: Settings = application.state.settings
    job = application.state.strapi_product_jobs[job_id]
    client = None
    drive_client = None
    balancer_catalog = None
    try:
        rows = read_product_rows(content)
        client = StrapiClient(settings.strapi_url, _token(settings), settings.strapi_product_endpoint, settings.strapi_timeout_seconds)
        drive_client = GoogleDriveClient(
            settings.google_drive_client_id.get_secret_value(),
            settings.google_drive_client_secret.get_secret_value(),
            settings.google_drive_refresh_token.get_secret_value(),
        )
        fichas_path = settings.fichas_path
        if fichas_content is not None:
            fichas = FichasLookup(fichas_content)
        else:
            if not fichas_path.is_file():
                downloads_path = Path.home() / "Downloads" / "fichas.xlsx"
                fichas_path = downloads_path if downloads_path.is_file() else fichas_path
            fichas = FichasLookup(fichas_path) if fichas_path.is_file() else None
        username = settings.lead_balancer_username
        password = settings.lead_balancer_password
        username = username.get_secret_value() if hasattr(username, "get_secret_value") else str(username)
        password = password.get_secret_value() if hasattr(password, "get_secret_value") else str(password)
        siu_key_lookup = None
        if username and password:
            balancer_catalog = BalancerProgramCatalog(settings.lead_balancer_url, username, password)
            siu_key_lookup = balancer_catalog.get_siu_key
        runner = StrapiDescriptionRunner(client, country_config.label, country_config.locale, dry_run=job["dry_run"], short_field=settings.strapi_short_description_field, long_field=settings.strapi_long_description_field, content_field=settings.strapi_content_description_field, programs_field=settings.strapi_programs_field, download_program_field=settings.strapi_download_program_field, experience_field=settings.strapi_experience_field, subjects_field=settings.strapi_subjects_field, siu_key_field=settings.strapi_siu_key_field, banner_key_field=settings.strapi_banner_key_field, siu_key_lookup=siu_key_lookup, fichas_lookup=fichas, title_field=settings.strapi_program_field, status=settings.strapi_content_status, google_drive_client=drive_client, product_schema=product_schema)
        results, summary = await runner.run(rows)
        report_dir = settings.storage_dir / "reports" / "strapi"
        report_dir.mkdir(parents=True, exist_ok=True)
        report_path = report_dir / f"{job_id}_{Path(filename).stem}_descriptions.xlsx"
        report_path.write_bytes(build_description_report(results, summary))
        job.update({"status": "SUCCESS" if not summary.failed and not summary.invalid_data else "WARNING", "completed": summary.total, "summary": summary.as_dict(), "results": [result.as_dict() for result in results], "report_path": str(report_path), "download_url": f"/api/strapi/products/jobs/{job_id}/download", "finished_at": datetime.now(timezone.utc).isoformat()})
    except Exception as error:  # noqa: BLE001
        job.update({"status": "FAILED", "message": str(error), "finished_at": datetime.now(timezone.utc).isoformat()})
    finally:
        if client:
            await client.close()
        if drive_client:
            await drive_client.close()
        if balancer_catalog:
            await balancer_catalog.close()
