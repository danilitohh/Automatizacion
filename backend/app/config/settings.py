"""Configuración centralizada y rutas de almacenamiento del proyecto."""

from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


# Este archivo está tres niveles por debajo de la raíz del proyecto:
# backend/app/config/settings.py -> raíz del proyecto.
PROJECT_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    """Valores que controlan el backend sin esconderlos dentro de los servicios."""

    app_env: str = "development"
    api_host: str = "127.0.0.1"
    api_port: int = 8000
    api_url: str = "http://127.0.0.1:8000"
    database_path: Path = PROJECT_ROOT / "storage" / "qa_automation.db"
    storage_dir: Path = PROJECT_ROOT / "storage"
    log_level: str = "INFO"

    # Estas variables se reservan para las fases que integrarán servicios externos.
    strapi_url: str = ""
    strapi_token: str = ""
    crm_url: str = ""
    crm_username: str = ""
    crm_password: str = ""
    inconcert_username: str = ""
    inconcert_password: str = ""

    # Servicios de IA: las claves se cargan desde .env y nunca se envían al renderer.
    ollama_api_key: SecretStr = SecretStr("")
    ollama_base_url: str = "https://ollama.com/api"
    ollama_model: str = "gpt-oss:120b"
    # Servidor de respaldo sin cuota de API. Requiere Ollama instalado y el modelo descargado.
    ollama_local_base_url: str = "http://127.0.0.1:11434/api"
    ollama_local_model: str = "gpt-oss:20b"
    groq_api_key: SecretStr = SecretStr("")
    groq_model: str = "llama-3.3-70b-versatile"
    gemini_api_key: SecretStr = SecretStr("")
    gemini_model: str = "gemini-2.5-flash"
    # Pausa entre filas cuando se ejecutan lotes UTEL-InConcert para
    # reducir bloqueos por tasa de solicitudes repetidas.
    batch_delay_seconds: int = 60

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    def ensure_directories(self) -> None:
        """Crea las carpetas que usarán las ejecuciones y los reportes."""

        # Las rutas relativas del .env se interpretan desde la raíz del proyecto,
        # aunque FastAPI haya sido iniciado desde la carpeta backend.
        if not self.storage_dir.is_absolute():
            self.storage_dir = PROJECT_ROOT / self.storage_dir
        if not self.database_path.is_absolute():
            self.database_path = PROJECT_ROOT / self.database_path

        self.storage_dir.mkdir(parents=True, exist_ok=True)
        for folder_name in (
            "logs",
            "reports",
            "screenshots",
            "visual_comparisons",
        ):
            (self.storage_dir / folder_name).mkdir(parents=True, exist_ok=True)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    """Devuelve una única configuración para toda la ejecución del backend."""

    return Settings()
