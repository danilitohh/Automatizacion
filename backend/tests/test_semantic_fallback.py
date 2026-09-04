"""Pruebas del orden de respaldo semántico sin llamar APIs externas."""

import asyncio

from backend.app.modules.pdp_validation.semantic_ai import SemanticAIOrchestrator
from backend.app.services.ai_service import AICompletion, AIProviderError


class FakeAIService:
    def __init__(self):
        self.calls = []

    def provider_statuses(self):
        return [
            {"provider": "gemini", "configured": True, "model": "test"},
            {"provider": "groq", "configured": True, "model": "test"},
            {"provider": "ollama", "configured": True, "model": "test"},
        ]

    async def generate(self, provider, prompt, *, system_instruction="", local=False):
        self.calls.append((provider, local))
        if provider == "gemini":
            raise AIProviderError("gemini", "cuota agotada", kind="quota", status_code=429)
        return AICompletion(
            provider=provider,
            model="test-model",
            text='{"matches":[{"expected_id":"e1","actual_id":"a1","confidence":0.9,"reason":"equivalencia"}]}',
        )


def test_semantic_fallback_uses_groq_after_gemini_quota():
    service = FakeAIService()
    orchestrator = SemanticAIOrchestrator(service)
    providers = []

    parsed, provider = asyncio.run(orchestrator._ask_with_fallback("{}", {"gemini": True, "groq": True, "ollama": True}, providers, stage="test"))

    assert provider == "groq"
    assert parsed["matches"]
    assert service.calls == [("gemini", False), ("groq", False)]
    assert providers[0]["status"] == "quota_exhausted"
    assert providers[1]["status"] == "ok"
