"""Contratos de entrada y salida del Bot de formularios."""

from typing import Literal

from pydantic import BaseModel, Field


BotStepType = Literal[
    "goto",
    "click",
    "hover",
    "check",
    "uncheck",
    "fill",
    "select",
    "assert_text",
    "assert_url",
    "wait",
    "screenshot",
    "scroll",
]


class BotStep(BaseModel):
    """Un paso pequeño y explícito que el ejecutor puede traducir a Playwright."""

    type: BotStepType
    target: str = ""
    value: str = ""


class BotConfig(BaseModel):
    """Configuración completa de un flujo web, sin secretos sensibles."""

    name: str = Field(min_length=1, max_length=120)
    url: str = Field(min_length=1, max_length=2000)
    browser: Literal["chromium", "chrome", "firefox", "webkit"] = "chromium"
    headless: bool = True
    steps: list[BotStep] = Field(min_length=1, max_length=100)


class BotStepResult(BaseModel):
    """Resultado legible de un paso individual."""

    step_number: int
    type: BotStepType
    status: Literal["PASS", "FAIL"]
    message: str
    screenshot: str | None = None


class BotRunResponse(BaseModel):
    """Resultado general que la interfaz mostrará al usuario."""

    status: Literal["PASS", "FAIL"]
    summary: str
    started_at: str
    finished_at: str
    duration_seconds: float
    steps: list[BotStepResult]
    screenshots: list[str] = []
