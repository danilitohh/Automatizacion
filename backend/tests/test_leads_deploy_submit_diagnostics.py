"""Mantiene el rechazo visual y la evidencia HTTP sin exponer credenciales."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from backend.app.config.settings import Settings
from backend.app.modules.bot_leads_deploy.runner import (
    RejectedSubmission, UnconfirmedSubmission, UtelInconcertRunner,
)


def test_server_error_with_support_toast_is_uncertain_and_excludes_personal_data():
    """Un toast genérico no demuestra que un HTTP 500 no haya creado el lead."""
    runner = UtelInconcertRunner(Settings())
    response = SimpleNamespace(status=500, text=AsyncMock(return_value='Internal server error'), request=SimpleNamespace(post_data_json={
        'formId': '151', 'integration': 'balanceador', 'token': 'SECRET_TOKEN',
        'inputs': {'first_name': 'PRIVATE_NAME', 'email': 'PRIVATE_EMAIL', 'phone': {'number': 'PRIVATE_PHONE'}, 'area': 'Diplomados', 'program': 'Programa', 'siuKey': None},
    }))
    with pytest.raises(UnconfirmedSubmission) as error:
        asyncio.run(runner._classify_utel_api_response(response, 'Error al enviar\nContacta a soporte'))
    message = str(error.value)
    assert 'HTTP 500' in message and 'Internal server error' in message
    assert '151' in message and 'balanceador' in message
    assert 'SECRET_TOKEN' not in message and 'PRIVATE_' not in message


@pytest.mark.parametrize('status', [400, 422])
def test_client_validation_error_remains_rejected(status):
    """Las respuestas de validación definitivas no se convierten en éxito."""
    runner = UtelInconcertRunner(Settings())
    response = SimpleNamespace(status=status, text=AsyncMock(return_value='Invalid input'))
    with pytest.raises(RejectedSubmission):
        asyncio.run(runner._classify_utel_api_response(response, 'Error al enviar. Contacta a soporte'))


def test_http_500_without_visible_rejection_remains_unconfirmed():
    runner = UtelInconcertRunner(Settings())
    response = SimpleNamespace(status=500, text=AsyncMock(return_value='Internal server error'), request=SimpleNamespace(post_data_json={}))
    with pytest.raises(UnconfirmedSubmission):
        asyncio.run(runner._classify_utel_api_response(response))
