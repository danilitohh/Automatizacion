"""Endpoints REST de la Fase 1."""

from datetime import datetime

from fastapi import APIRouter, Query, Request

from ..schemas.execution import (
    DashboardSummary,
    ExecutionListResponse,
    HealthResponse,
)
from ..services.dashboard_service import DashboardService
from ..services.logging_service import get_logger


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
