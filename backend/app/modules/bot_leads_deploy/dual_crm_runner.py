"""Verificación dual de leads exclusiva para Bot Leads Deploy.

La columna ``Url Origen Lead`` se usa como destino preferido, no como destino
único. Si el lead no puede confirmarse allí después de un envío real, el módulo
consulta el otro CRM sin volver a enviar el formulario de UTEL.
"""

from __future__ import annotations

from typing import Any, Callable

from ...schemas.bot import UtelQaConfig
from .runner import RejectedSubmission, UtelInconcertRunner, UtelQaError
from .service import LeadsDeploySpreadsheetService


class LeadsDeployDualCrmRunner(UtelInconcertRunner):
    """Busca el lead en InConcert y Balanceador de forma segura y secuencial."""

    async def _submit_utel_form(
        self,
        page: Any,
        form: Any,
        should_stop: Callable[[], bool] | None = None,
    ) -> None:
        """No consulta CRM cuando UTEL confirma un rechazo del formulario.

        El runner base trata cualquier POST como una señal que merece conciliación
        para evitar duplicados. En Leads Deploy distinguimos el caso explícito de
        rechazo: si UTEL devuelve un rechazo concluyente, el lead no se considera
        enviado y no tiene sentido abrir InConcert ni Balanceador.

        Las respuestas inciertas (por ejemplo HTTP 5xx o pérdida de respuesta)
        siguen usando la lógica segura existente: verificar CRM y nunca reenviar.
        """

        try:
            await super()._submit_utel_form(page, form, should_stop)
        except RejectedSubmission as error:
            raise UtelQaError(
                "utel_submit",
                (
                    f"{error} UTEL confirmó que el formulario no fue aceptado; "
                    "Leads Deploy no consultará InConcert ni Balanceador para este caso."
                ),
                error.selector,
            ) from error

    @staticmethod
    def _failed_stage_name(result: dict[str, Any]) -> str:
        for stage in result.get("stages", []):
            if isinstance(stage, dict):
                status = stage.get("status")
                name = stage.get("stage")
            else:
                status = getattr(stage, "status", None)
                name = getattr(stage, "stage", None)
            if status == "FAIL":
                return str(name or "")
        return ""

    def _secondary_verification_config(
        self,
        config: UtelQaConfig,
        primary_result: dict[str, Any],
    ) -> UtelQaConfig | None:
        """Construye una segunda consulta CRM sin permitir un nuevo envío UTEL."""

        if primary_result.get("lead_url"):
            return None
        if primary_result.get("status") != "FAIL":
            return None

        # Nunca iniciar una búsqueda CRM si la etapa que falló fue el envío.
        # Esto cubre rechazos explícitos de UTEL y evita buscar leads inexistentes.
        failed_stage = self._failed_stage_name(primary_result)
        if failed_stage == "utel_submit":
            return None

        # Solo se permite buscar en el segundo CRM si el formulario ya fue
        # enviado, o si esta ejecución ya era una conciliación verification_only.
        if not config.verification_only and primary_result.get("utel_submission_attempted") is not True:
            return None

        origin_is_balanceador = self._lead_origin_is_balanceador(config)

        if origin_is_balanceador:
            if failed_stage and not failed_stage.startswith("lead_balancer_"):
                return None
            inconcert_url = LeadsDeploySpreadsheetService.default_inconcert_url(
                config.country
            )
            if not inconcert_url:
                self.logger.warning(
                    "Leads Deploy no tiene URL InConcert configurada para %s; "
                    "no se puede ejecutar la verificación secundaria.",
                    config.country,
                )
                return None
            return config.model_copy(
                update={
                    "verification_only": True,
                    "defer_crm_verification": False,
                    # Vaciar el origen hace que el runner base intente InConcert.
                    "lead_origin_url": "",
                    "inconcert_url": inconcert_url,
                    "keep_browser_open": False,
                }
            )

        # Si InConcert no pudo completar la verificación, intentar Balanceador.
        # El runner base ya hace InConcert -> Balanceador cuando el fallo es
        # inconcert_search; esta rama cubre también open/login/contacts.
        if failed_stage and not failed_stage.startswith("inconcert_"):
            return None
        balancer_url = str(self.settings.lead_balancer_url or "").strip()
        if not balancer_url:
            return None
        return config.model_copy(
            update={
                "verification_only": True,
                "defer_crm_verification": False,
                "lead_origin_url": balancer_url,
                "inconcert_url": balancer_url,
                # Balanceador puede presentar Cloudflare; mantener Chrome visible
                # conserva el perfil QA que ya usa este módulo.
                "browser": "chrome",
                "headless": False,
                "keep_browser_open": False,
            }
        )

    @staticmethod
    def _merge_dual_results(
        original_config: UtelQaConfig,
        primary: dict[str, Any],
        secondary: dict[str, Any],
    ) -> dict[str, Any]:
        """Une evidencia de ambos CRM sin perder el estado del envío original."""

        merged = {**primary, **secondary}
        merged["stages"] = [
            *primary.get("stages", []),
            *secondary.get("stages", []),
        ]
        merged["screenshots"] = list(
            dict.fromkeys(
                [
                    *primary.get("screenshots", []),
                    *secondary.get("screenshots", []),
                ]
            )
        )
        merged["selected_program_name"] = (
            primary.get("selected_program_name")
            or secondary.get("selected_program_name")
            or ""
        )
        merged["program_selection_notice"] = (
            primary.get("program_selection_notice")
            or secondary.get("program_selection_notice")
            or ""
        )
        merged["utel_submission_attempted"] = primary.get(
            "utel_submission_attempted",
            False,
        )

        secondary_confirmed = (
            secondary.get("status") == "PASS"
            and secondary.get("lead_found") == "success"
            and bool(secondary.get("lead_url"))
        )

        if secondary_confirmed:
            source = str(secondary.get("lead_source") or "CRM")
            merged["status"] = "PASS"
            merged["lead_found"] = "success"
            merged["lead_source"] = source
            merged["lead_url"] = secondary.get("lead_url")
            merged["summary"] = (
                f"Lead localizado en {source} después de consultar el destino "
                "alterno de Leads Deploy."
            )
            if original_config.verification_only:
                merged["utel_submission"] = primary.get(
                    "utel_submission",
                    "skipped",
                )
                merged["utel_submission_message"] = primary.get(
                    "utel_submission_message",
                    "Envío ya realizado; verificación CRM completada.",
                )
            else:
                merged["utel_submission"] = "success"
                merged["utel_submission_message"] = (
                    f"Lead confirmado en {source} sin reenviar el formulario."
                )
            return merged

        # Ningún segundo intento puede provocar un reenvío. Se conserva el
        # estado de envío del primer resultado y se reportan ambas evidencias.
        merged["status"] = "FAIL"
        merged["utel_submission"] = primary.get(
            "utel_submission",
            merged.get("utel_submission", "pending"),
        )
        merged["utel_submission_message"] = primary.get(
            "utel_submission_message",
            merged.get("utel_submission_message", ""),
        )
        merged["summary"] = (
            "No se pudo confirmar el lead después de consultar InConcert y "
            "Balanceador. El formulario no se reenvió."
        )
        return merged

    async def run(
        self,
        config: UtelQaConfig,
        should_stop: Callable[[], bool] | None = None,
    ) -> dict[str, Any]:
        """Usa Url Origen Lead como prioridad y el otro CRM como respaldo."""

        primary = await super().run(config, should_stop)
        secondary_config = self._secondary_verification_config(config, primary)
        if secondary_config is None:
            return primary

        preferred = (
            "Balanceador"
            if self._lead_origin_is_balanceador(config)
            else "InConcert"
        )
        alternate = "InConcert" if preferred == "Balanceador" else "Balanceador"
        self.logger.warning(
            "Lead no confirmado en %s; Leads Deploy consultará también %s sin reenviar UTEL.",
            preferred,
            alternate,
        )

        secondary = await super().run(secondary_config, should_stop)
        return self._merge_dual_results(config, primary, secondary)
