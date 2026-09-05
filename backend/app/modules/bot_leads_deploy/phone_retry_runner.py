"""Reintento de teléfono exclusivo de Bot Leads Deploy.

Cuando UTEL confirma un rechazo explícito del formulario (por ejemplo el toast
"Error al enviar / Contacta a soporte"), este adaptador marca el resultado para
que el batch existente reserve otro lead de prueba y pruebe con un teléfono
diferente. No cambia la lógica de otros módulos.
"""

from __future__ import annotations

from typing import Any, Callable

from .dual_crm_runner import LeadsDeployDualCrmRunner
from .runner import UtelQaError


class LeadsDeployPhoneRetryRunner(LeadsDeployDualCrmRunner):
    """Convierte rechazos explícitos de UTEL en candidatos a otro teléfono."""

    async def _submit_utel_form(
        self,
        page: Any,
        form: Any,
        should_stop: Callable[[], bool] | None = None,
    ) -> None:
        try:
            await super()._submit_utel_form(page, form, should_stop)
        except UtelQaError as error:
            if error.stage != "utel_submit":
                raise

            message = str(error)
            normalized = message.casefold()
            explicit_rejection = (
                "utel confirmó que el formulario no fue aceptado" in normalized
                or "utel confirmo que el formulario no fue aceptado" in normalized
            )
            if not explicit_rejection:
                raise

            # El worker batch ya tiene una política segura de hasta 3 intentos
            # para mensajes "Error al enviar" / "Contacta a soporte". Incluir
            # esas señales aquí hace que Leads Deploy reserve otro teléfono sin
            # tocar la lógica global ni consultar CRM por el número rechazado.
            raise UtelQaError(
                "utel_submit",
                (
                    "Error al enviar / Contacta a soporte. "
                    f"{message} Leads Deploy reintentará este caso con otro "
                    "teléfono de prueba antes de marcarlo como fallo definitivo."
                ),
                error.selector,
            ) from error
