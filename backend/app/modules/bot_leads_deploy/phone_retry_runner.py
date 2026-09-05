"""Reintento de teléfono exclusivo de Bot Leads Deploy.

Cuando UTEL confirma un rechazo explícito del formulario (por ejemplo el toast
"Error al enviar / Contacta a soporte"), este adaptador marca el resultado para
que el batch existente reserve otro lead de prueba y pruebe con un teléfono
diferente. También mantiene visible el feedback de UTEL en ejecuciones Chrome.
No cambia la lógica de otros módulos.
"""

from __future__ import annotations

import asyncio
from contextlib import suppress
from typing import Any, Callable

from .dual_crm_runner import LeadsDeployDualCrmRunner
from .runner import UtelQaError


class LeadsDeployPhoneRetryRunner(LeadsDeployDualCrmRunner):
    """Convierte rechazos explícitos de UTEL en candidatos a otro teléfono."""

    async def _maximize_visible_browser(self, page: Any) -> None:
        """Maximiza Chrome sin modificar el layout lógico del formulario.

        Leads Deploy usa Chrome visible especialmente cuando interviene el
        Balanceador. El viewport fijo del runner puede dejar mensajes de UTEL
        pegados al borde inferior; maximizar la ventana aprovecha el área real
        disponible del monitor antes de hacer clic en Enviar información.
        """

        try:
            session = await page.context.new_cdp_session(page)
            window = await session.send("Browser.getWindowForTarget")
            window_id = window.get("windowId")
            if window_id is not None:
                await session.send(
                    "Browser.setWindowBounds",
                    {
                        "windowId": window_id,
                        "bounds": {"windowState": "maximized"},
                    },
                )
                await asyncio.sleep(0.35)
            await session.detach()
        except Exception:
            # Firefox/WebKit o versiones de Chromium que no expongan CDP deben
            # continuar con normalidad; esto es únicamente una mejora visual.
            return

    async def _surface_utel_feedback(self, page: Any) -> None:
        """Mueve toasts/alertas a una zona visible para revisión manual."""

        try:
            await page.evaluate(
                """() => {
                    const selectors = [
                      '#chakra-toast-manager-bottom',
                      '[role="alert"]',
                      '[role="status"]',
                      '.chakra-alert',
                      '.chakra-toast',
                      '.chakra-form__error-message'
                    ];
                    const nodes = selectors.flatMap(selector =>
                      [...document.querySelectorAll(selector)]
                    ).filter(node => node.getClientRects().length > 0);
                    if (!nodes.length) return false;

                    for (const node of nodes) {
                      const container = node.id === 'chakra-toast-manager-bottom'
                        ? node
                        : node.closest('#chakra-toast-manager-bottom') || node;
                      container.style.setProperty('z-index', '2147483647', 'important');
                      if (container.id === 'chakra-toast-manager-bottom') {
                        container.style.setProperty('bottom', '72px', 'important');
                      }
                    }

                    const last = nodes[nodes.length - 1];
                    last.scrollIntoView({ block: 'center', inline: 'nearest', behavior: 'auto' });
                    return true;
                }"""
            )
            # Deja el aviso visible un instante antes de que el flujo cambie de
            # pestaña o abra CRM, útil tanto para QA como para capturas manuales.
            await asyncio.sleep(0.8)
        except Exception:
            return

    async def _wait_for_utel_submit_feedback(self, page: Any) -> str:
        """Conserva la detección estable y además hace visible el mensaje."""

        text = await super()._wait_for_utel_submit_feedback(page)
        await self._surface_utel_feedback(page)
        return text

    async def _submit_utel_form(
        self,
        page: Any,
        form: Any,
        should_stop: Callable[[], bool] | None = None,
    ) -> None:
        await self._maximize_visible_browser(page)
        try:
            await super()._submit_utel_form(page, form, should_stop)
        except UtelQaError as error:
            # Si hubo un aviso visible, mantenerlo accesible antes de cambiar de
            # número o terminar el caso. No altera la clasificación del error.
            with suppress(Exception):
                await self._surface_utel_feedback(page)

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
