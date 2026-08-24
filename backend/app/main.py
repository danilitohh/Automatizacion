"""Punto de entrada de FastAPI para la plataforma de QA."""

from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .automations.generic_bot.recorder import RecorderManager
from .api.routes import router
from .config.settings import Settings, get_settings
from .database.connection import initialize_database
from .services.logging_service import configure_logging, get_logger


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    """Prepara carpetas, base de datos y logs antes de atender solicitudes."""

    settings: Settings = application.state.settings
    settings.ensure_directories()
    configure_logging(settings.storage_dir, settings.log_level).info(
        "Backend iniciado en %s:%s", settings.api_host, settings.api_port
    )
    initialize_database(settings.database_path)
    try:
        yield
    finally:
        await application.state.recorder_manager.close_all()


def create_app(settings: Settings | None = None) -> FastAPI:
    """Construye la aplicación para producción y para tests aislados."""

    application = FastAPI(
        title="QA Automation API",
        version="0.1.0",
        description="Backend local para automatizaciones de QA.",
        lifespan=lifespan,
    )
    # Electron carga el frontend desde file://, cuyo origen se presenta como
    # "null". Solo se permiten orígenes locales porque esta API no es pública.
    application.add_middleware(
        CORSMiddleware,
        allow_origins=["null", "http://localhost:3000", "http://127.0.0.1:3000"],
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["*"],
    )

    @application.exception_handler(Exception)
    async def unexpected_error_handler(request: Request, error: Exception) -> JSONResponse:
        """Registra el detalle técnico y entrega un mensaje apto para la interfaz."""

        get_logger().error(
            "Error no controlado en %s %s",
            request.method,
            request.url.path,
            exc_info=(type(error), error, error.__traceback__),
        )
        return JSONResponse(
            status_code=500,
            content={
                "detail": "No fue posible completar la operación. Revisa los logs del backend.",
                "error_code": "INTERNAL_ERROR",
            },
        )

    application.state.settings = settings or get_settings()
    application.state.recorder_manager = RecorderManager()
    application.include_router(router)
    return application


app = create_app()
