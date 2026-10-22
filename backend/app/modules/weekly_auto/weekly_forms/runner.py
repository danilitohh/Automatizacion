"""Runner semántico de Weekly Forms sobre el flujo UTEL -> CRM existente."""

from __future__ import annotations

import asyncio
import re
import secrets
from contextlib import suppress
from time import perf_counter
from typing import Any, Callable
from urllib.parse import urlparse

from ...bot_leads_deploy.phone_retry_runner import LeadsDeployPhoneRetryRunner
from ...bot_leads_deploy.runner import (
    RejectedSubmission,
    UnconfirmedSubmission,
    UtelQaError,
)
from .schemas import WeeklyFormsCaseConfig


class WeeklyFormsRunner(LeadsDeployPhoneRetryRunner):
    """Detecta controles por semántica y reutiliza la búsqueda dual de CRM."""

    GENERIC_FORM_TIMEOUT_MS = 30000
    DOCUMENT_FIELD_PATTERN = (
        r"document|identificaci[oó]n|identificacion|identidad|identity|"
        r"c[eé]dula|cedula|\bdni\b|passport|numero.*documento|document.*number"
    )

    def _is_generic_lp(self, config: WeeklyFormsCaseConfig | None = None) -> bool:
        current = config or getattr(self, "_rotation_config", None)
        return getattr(current, "weekly_form_type", "") == "form_lp"

    async def _navigate_utel(self, page: Any, config: WeeklyFormsCaseConfig) -> None:
        if self._is_generic_lp(config):
            return
        await super()._navigate_utel(page, config)

    async def _find_utel_form(self, page: Any, config: WeeklyFormsCaseConfig) -> Any:
        if not self._is_generic_lp(config):
            return await super()._find_utel_form(page, config)

        await self._check_access(page)
        deadline = perf_counter() + (self.GENERIC_FORM_TIMEOUT_MS / 1000)
        while perf_counter() < deadline:
            candidate = await self._best_semantic_form(page)
            if candidate is not None:
                await candidate.scroll_into_view_if_needed()
                # Las LP de UTEL renderizan primero el HTML y habilitan el
                # botón cuando termina de cargar su librería de formularios.
                # Esperar aquí evita pulsar un botón visualmente presente pero
                # todavía marcado con ``data-ic-button-disabled``.
                with suppress(Exception):
                    await page.wait_for_function(
                        """() => {
                          const button = document.querySelector(
                            'form button[type="submit"], form input[type="submit"]'
                          );
                          return button && !button.disabled
                            && !button.hasAttribute('data-ic-button-disabled')
                            && button.getClientRects().length > 0;
                        }""",
                        timeout=12000,
                    )
                return candidate
            await asyncio.sleep(0.5)
        raise UtelQaError(
            "weekly_manual",
            "La página no contiene un formulario de lead utilizable. La celda Lead "
            "se dejará en blanco para completar esta fila manualmente.",
            "form:has(input), .formio-form",
        )

    async def _best_semantic_form(self, page: Any) -> Any | None:
        """Elige el formulario visible con datos de contacto, no newsletter/login."""

        best: tuple[int, Any] | None = None
        for frame in page.frames:
            for selector in ("form", ".formio-form"):
                candidates = frame.locator(selector)
                for index in range(await candidates.count()):
                    candidate = candidates.nth(index)
                    try:
                        if not await candidate.is_visible():
                            continue
                        score = await candidate.evaluate(
                            """element => {
                                const style = getComputedStyle(element);
                                const box = element.getBoundingClientRect();
                                // Algunas LP montan una variante desktop/móvil oculta
                                // que Playwright considera visible por tener layout.
                                if (style.display === 'none' || style.visibility === 'hidden'
                                  || Number.parseFloat(style.opacity || '1') === 0
                                  || box.width === 0 || box.height === 0) return -100;
                                const controls = [...element.querySelectorAll('input, select, textarea')];
                                const text = (element.innerText || '').toLowerCase();
                                const signature = controls.map(control => [
                                  control.name, control.id, control.type,
                                  control.placeholder, control.getAttribute('aria-label')
                                ].filter(Boolean).join(' ')).join(' ').toLowerCase();
                                const hasName = /nombre|name|first.?name/.test(signature + ' ' + text);
                                const hasEmail = /correo|email|e-mail/.test(signature + ' ' + text);
                                const hasPhone = /telefono|teléfono|celular|movil|móvil|phone|cellphone/.test(signature + ' ' + text);
                                const hasAcademic = /programa|program|area|área|interes|interés/.test(signature + ' ' + text);
                                const bad = /iniciar sesi[oó]n|login|newsletter|suscr[ií]b/.test(text);
                                return (hasName ? 5 : 0) + (hasEmail ? 7 : 0) + (hasPhone ? 4 : 0)
                                  + (hasAcademic ? 3 : 0) + Math.min(controls.length, 8) - (bad ? 12 : 0);
                            }"""
                        )
                    except Exception:
                        continue
                    if score >= 14 and (best is None or score > best[0]):
                        best = (score, candidate)
        return best[1] if best else None

    async def _is_rendered_control(self, field: Any) -> bool:
        """Evita duplicados ocultos que comparten los mismos nombres de campo."""

        try:
            return bool(await field.evaluate(
                """element => {
                  const style = getComputedStyle(element);
                  const box = element.getBoundingClientRect();
                  return style.display !== 'none' && style.visibility !== 'hidden'
                    && Number.parseFloat(style.opacity || '1') > 0
                    && box.width > 0 && box.height > 0;
                }"""
            ))
        except Exception:
            return await field.is_visible()

    async def _fill_utel_form(self, page: Any, form: Any, config: WeeklyFormsCaseConfig) -> None:
        # El campo puede aparecer en cualquier variante de formulario del lote.
        await self._fill_document_number(form, config)
        if not self._is_generic_lp(config):
            if config.program_name:
                await super()._fill_utel_form(page, form, config)
            else:
                await self._fill_blc_without_catalog_program(page, form, config)
            return

        await self._fill_semantic_input(
            form,
            r"(?:^|\b)(?:nombre|name|first.?name|fullname|full.?name)(?:\b|$)",
            config.lead.name,
            required=True,
        )
        await self._fill_semantic_input(
            form,
            r"correo|email|e-mail",
            config.lead.email,
            required=True,
        )
        await self._fill_semantic_input(
            form,
            r"telefono|teléfono|celular|movil|móvil|phone|cellphone|mobile",
            config.lead.phone,
            required=False,
        )
        await self._fill_required_date_fields(form)

        selects = form.locator("select")
        for index in range(await selects.count()):
            field = selects.nth(index)
            if not await field.is_visible() or not await self._is_rendered_control(field):
                continue
            descriptor = self._normalize(await self._control_descriptor(field))
            # Varias LP rotulan horario, bachillerato y lada como Licenciaturas.
            # Reconocer primero esos controles evita sobrescribir el programa.
            if re.search(r"bachiller|titulo|t[ií]tulo|graduaste|secundaria|high.?school", descriptor):
                await self._select_semantic_option(field, "si", "first")
            elif re.search(r"codigo.*pais|country.*code|indicativo|lada|prefix|pais|country", descriptor):
                await self._select_semantic_option(field, config.country, "country")
            elif re.search(r"estado|state|ciudad|city|provincia|residencia|location|ubicacion", descriptor):
                await self._select_semantic_option(field, "", "first")
            elif re.search(r"horario|hora|time|schedule", descriptor):
                await self._select_semantic_option(field, "", "first")
            elif re.search(r"canal|contacto|contact.?method", descriptor):
                await self._select_semantic_option(field, "", "first")
            elif re.search(r"programa|program|carrera|curso|producto|licenciatura|maestria|master", descriptor):
                selected = await self._select_semantic_option(
                    field, config.program_name or config.level, "program",
                )
                if selected:
                    self.selected_program_name = selected
            elif re.search(r"area|nivel|level|grado|interes", descriptor):
                await self._select_semantic_option(field, config.level, "level")
                # Espera el catálogo dependiente del nivel seleccionado.
                await asyncio.sleep(0.8)

        # Radios y selects no etiquetados que sean obligatorios también reciben
        # una opción válida. Así se cubren LP antiguas con nombres input_9.
        for index in range(await selects.count()):
            field = selects.nth(index)
            if await field.is_visible() and await self._is_rendered_control(field) and not await self._has_real_select_value(field):
                await self._select_semantic_option(field, config.level, "first")

        radios = form.locator('input[type="radio"]:not(:checked)')
        for index in range(await radios.count()):
            radio = radios.nth(index)
            if not await self._is_rendered_control(radio) or await radio.get_attribute("required") is None:
                continue
            descriptor = self._normalize(await self._control_descriptor(radio))
            if re.search(r"privacidad|privacy|marketing|publicidad|promocion|promoción|contact", descriptor):
                continue
            with suppress(Exception):
                await radio.check(force=True)
            if await form.locator('input[type="radio"]:checked').count():
                break

        checkboxes = form.locator('input[type="checkbox"]')
        for index in range(await checkboxes.count()):
            checkbox = checkboxes.nth(index)
            if not await checkbox.is_visible() or not await self._is_rendered_control(checkbox):
                continue
            descriptor = self._normalize(await self._control_descriptor(checkbox))
            if re.search(r"privacidad|privacy|politica|policy|terminos|terms|aviso", descriptor):
                await self._ensure_checkbox_checked(checkbox)

        await asyncio.sleep(0.8)
        await self._validate_generic_form(form)

    async def _fill_required_date_fields(self, form: Any) -> None:
        """Completa fechas QA obligatorias que algunas LP agregan al formulario."""

        # Algunas LP declaran la fecha como texto (por ejemplo
        # ``FechaNacimiento-input``) aunque la validación HTML la trate como
        # obligatoria; por eso se inspeccionan también inputs semánticos.
        fields = form.locator("input, textarea")
        for index in range(await fields.count()):
            field = fields.nth(index)
            if not await field.is_visible() or not await self._is_rendered_control(field) or await field.is_disabled():
                continue
            input_type = (await field.get_attribute("type") or "text").lower()
            if input_type in {"hidden", "checkbox", "radio", "file", "submit", "button"}:
                continue
            descriptor = self._normalize(await self._control_descriptor(field))
            required = await field.get_attribute("required") is not None
            if not required and not re.search(r"fecha|nacimiento|birth|date", descriptor):
                continue
            if (await field.input_value()).strip():
                continue
            # Fecha adulta sintética y estable para validaciones QA; no representa
            # la identidad de una persona real.
            await field.fill("1990-01-15")
            await field.press("Tab")

    async def _fill_document_number(self, form: Any, config: WeeklyFormsCaseConfig) -> None:
        """Completa documentos visibles en cualquier variante de Weekly Forms."""

        controls = form.locator(
            'input:not([type="hidden"]):not([type="checkbox"]):not([type="radio"]), textarea'
        )
        for index in range(await controls.count()):
            field = controls.nth(index)
            if not await field.is_visible() or await field.is_disabled():
                continue
            descriptor = self._normalize(await self._control_descriptor(field))
            if not re.search(self.DOCUMENT_FIELD_PATTERN, descriptor, re.I):
                continue

            # No se inventa identidad nacional salvo el QA sintético habilitado
            # por el lote colombiano; el Excel puede proporcionar uno aprobado.
            value = str(getattr(config.lead, "document_number", "") or "").strip()
            required = (
                (config.qa_document_required and self._normalize(config.country) == "colombia")
                or await field.get_attribute("required") is not None
                or await field.get_attribute("aria-required") == "true"
            )
            if value:
                await field.fill(value)
                await field.press("Tab")
            elif required:
                raise UtelQaError(
                    "utel_fill",
                    "La landing solicita número de documento y esta fila no tiene un dato QA. "
                    "Agrega el valor autorizado en la columna Documento de prueba.",
                    self.DOCUMENT_FIELD_PATTERN,
                )
            return

    async def _fill_blc_without_catalog_program(
        self,
        page: Any,
        form: Any,
        config: WeeklyFormsCaseConfig,
    ) -> None:
        """Completa un BLC de QA escogiendo una opción real del nivel indicado."""

        await self._apply_deploy_modality(form, config)
        if config.form_type != "tarjeta":
            level = form.locator('[data-cy="educationLevelInput"]').first
            if await level.count() and not await self._has_academic_selection(level):
                if getattr(config, "randomize_academic_selections", False):
                    await self._select_random_level(level)
                else:
                    await self._set_dynamic_field(form, '[data-cy="educationLevelInput"]', config.level)
            await self._select_random_program(page, form, '[data-cy="productsInput"]', config)

        await self._select_optional_bachillerato(form)
        await self._select_random_city(form)
        await self._select_preferred_contact_channel(form)
        await self._fill_first_available(form, [
            '[data-cy="textfieldInput"]', '#first_name', 'input[name="first_name"]',
            'input[placeholder*="Nombre" i]', 'input[placeholder*="name" i]',
        ], config.lead.name)
        await self._fill_first_available(form, [
            '[data-cy="emailInput"]', '#email', 'input[type="email"]', 'input[name="email"]',
            'input[placeholder*="Correo" i]', 'input[placeholder*="email" i]',
        ], config.lead.email)
        await self._set_country_if_possible(form, config.country)
        await self._fill_first_available(form, [
            '[data-cy="telephoneInput"]', '#phone', 'input[type="tel"]', 'input[name="phone"]',
            'input[placeholder*="Teléfono" i]', 'input[placeholder*="Telefono" i]',
            'input[placeholder*="phone" i]',
        ], config.lead.phone)
        await self._check_privacy(form)

    async def _select_random_level(self, field: Any) -> str:
        """Elige un nivel real en BLC y espera a que React cargue programas."""

        tag_name = await field.evaluate("element => element.tagName.toLowerCase()")
        if tag_name != "select":
            await self._set_dynamic_field(
                field.locator("xpath=.."),
                '[data-cy="educationLevelInput"]',
                getattr(getattr(self, "_rotation_config", None), "level", "Licenciatura"),
            )
            return ""
        await field.wait_for(state="visible", timeout=12000)
        await self._wait_for_select_options(field)
        options = await field.locator("option").evaluate_all(
            """items => items.map(item => ({value: item.value || '', text: (item.textContent || '').trim(), disabled: item.disabled}))"""
        )
        real = [
            item for item in options
            if item["value"] and not item["disabled"]
            and not re.search(r"seleccion|select|opcion|option|cargando|loading", self._normalize(item["text"]))
        ]
        if not real:
            raise UtelQaError("utel_fill", "El formulario no contiene niveles disponibles.", '[data-cy="educationLevelInput"]')
        selected = secrets.choice(real)
        await field.select_option(value=selected["value"])
        await field.dispatch_event("change")
        await asyncio.sleep(0.8)
        return selected["text"]

    async def _fill_semantic_input(self, form: Any, pattern: str, value: str, *, required: bool) -> None:
        controls = form.locator('input:not([type="hidden"]):not([type="checkbox"]):not([type="radio"]), textarea')
        matches = []
        for index in range(await controls.count()):
            field = controls.nth(index)
            if not await field.is_visible() or not await self._is_rendered_control(field) or await field.is_disabled():
                continue
            descriptor = self._normalize(await self._control_descriptor(field))
            if re.search(pattern, descriptor, re.I):
                matches.append(field)
        if not matches:
            if required:
                raise UtelQaError(
                    "utel_fill",
                    "El formulario existe, pero no se encontró un campo obligatorio de contacto.",
                    pattern,
                )
            return
        field = matches[0]
        await field.fill(value)
        await field.press("Tab")

    async def _control_descriptor(self, field: Any) -> str:
        """Describe solo el control; un contenedor compartido no es su etiqueta."""
        return await field.evaluate(
            """element => {
                const parent = element.parentElement;
                // Las LP antiguas agrupan todo el formulario en un mismo div.
                // Solo usar su texto cuando pertenece a un único control.
                const localText = parent?.querySelectorAll('input, select, textarea').length === 1
                  ? [...parent.childNodes].filter(node => node.nodeType === 3)
                      .map(node => node.textContent).join(' ') : '';
                const label = element.labels?.[0]?.innerText
                  || element.closest('label')?.innerText
                  || (element.id ? document.querySelector(`label[for="${CSS.escape(element.id)}"]`)?.innerText : '')
                  || localText;
                const labelledBy = element.getAttribute('aria-labelledby')
                  ?.split(/\\s+/).map(id => document.getElementById(id)?.innerText || '').join(' ') || '';
                return [element.name, element.id, element.type, element.placeholder,
                  element.getAttribute('aria-label'), labelledBy, element.dataset?.cy, label,
                  element.tagName === 'SELECT' && !element.options[0]?.value
                    ? element.options[0]?.textContent : '']
                  .filter(Boolean).join(' ');
            }"""
        )

    async def _ensure_checkbox_checked(self, checkbox: Any) -> None:
        """Activa checkboxes nativos y wrappers que cancelan el clic directo."""

        if await checkbox.is_checked():
            return
        with suppress(Exception):
            await checkbox.check(force=True, timeout=3000)
        if await checkbox.is_checked():
            return

        checkbox_id = await checkbox.get_attribute("id")
        if checkbox_id:
            with suppress(Exception):
                await checkbox.evaluate(
                    "element => document.querySelector(`label[for=\"${CSS.escape(element.id)}\"]`)?.click()"
                )
        if await checkbox.is_checked():
            return

        await checkbox.evaluate(
            """element => {
                element.checked = true;
                element.setAttribute('checked', 'checked');
                element.dispatchEvent(new Event('input', {bubbles: true}));
                element.dispatchEvent(new Event('change', {bubbles: true}));
            }"""
        )
        if not await checkbox.is_checked():
            raise UtelQaError(
                "utel_fill",
                "No se pudo aceptar el aviso o política de privacidad.",
                'input[type="checkbox"]',
            )

    async def _has_real_select_value(self, field: Any) -> bool:
        value = self._normalize(await field.input_value())
        label = self._normalize(
            await field.evaluate("element => element.selectedOptions[0]?.textContent || ''")
        )
        placeholder = re.compile(r"seleccion|select|opcion|option|programa|program|area|interes|cargando|loading")
        return bool(value and label and not placeholder.search(label))

    async def _select_semantic_option(self, field: Any, expected: str, kind: str) -> str:
        # Los formularios pueden iniciar con un país distinto al de la fila;
        # solo se conserva la selección previa para los demás campos.
        has_current_value = await self._has_real_select_value(field)
        current_value = await field.input_value() if has_current_value else ""
        current_label = (
            await field.evaluate("element => element.selectedOptions[0]?.textContent || ''")
            if has_current_value
            else ""
        ).strip()
        if has_current_value and kind != "country":
            return current_label
        deadline = perf_counter() + (12 if kind == "program" else 2)
        real = []
        while perf_counter() < deadline:
            options = await field.locator("option").evaluate_all(
                """items => items.map(item => ({value: item.value || '', text: (item.textContent || '').trim(), disabled: item.disabled}))"""
            )
            real = [
                item for item in options
                if item["value"] and not item["disabled"] and not re.search(
                    r"seleccion|select|opcion|option|programa de interes|area de interes|cargando|loading",
                    self._normalize(item["text"]),
                )
            ]
            if real:
                break
            await asyncio.sleep(0.35)
        if not real:
            return ""
        normalized_expected = self._normalize(expected)
        aliases = [normalized_expected]
        if kind == "level":
            if "licenc" in normalized_expected:
                aliases += ["licenciatura", "carrera", "bachelor"]
            elif "maestr" in normalized_expected or "master" in normalized_expected:
                aliases += ["maestria", "master"]
            elif "diplom" in normalized_expected:
                aliases += ["diplomado", "educacion continua"]
        elif kind == "country":
            country_codes = {
                "mexico": ("méxico", "+52"),
                "usa": ("estados unidos", "united states", "+1"),
                "united states": ("estados unidos", "usa", "+1"),
                "estados unidos": ("united states", "usa", "+1"),
                "colombia": ("colombia", "+57"),
                "ecuador": ("ecuador", "+593"),
                "peru": ("perú", "+51"),
                "argentina": ("argentina", "+54"),
                "bolivia": ("bolivia", "+591"),
                "dominicana": ("republica dominicana", "dominican republic", "+1"),
                "republica dominicana": ("dominicana", "dominican republic", "+1"),
                "chile": ("chile", "+56"),
                "paraguay": ("paraguay", "+595"),
                "guatemala": ("guatemala", "+502"),
                "panama": ("panamá", "+507"),
                "el salvador": ("el salvador", "+503"),
                "filipinas": ("philippines", "+63"),
                "philippines": ("filipinas", "+63"),
                "indonesia": ("indonesia", "+62"),
                "vietnam": ("vietnam", "viet nam", "+84"),
                "india": ("india", "+91"), "singapur": ("singapore", "singapur", "+65"),
                "singapore": ("singapur", "+65"),
            }
            aliases += list(country_codes.get(normalized_expected, ()))
        matching = [
            item for item in real
            if any(alias and alias in self._normalize(item["text"]) for alias in aliases)
        ]
        if kind == "country" and not matching:
            raise UtelQaError(
                "utel_fill",
                f"No se encontró la opción del país {expected!r} en el formulario; se detuvo para no enviar el lead a otro país.",
                await self._control_descriptor(field),
            )
        if kind == "country" and current_value and any(
            item["value"] == current_value for item in matching
        ):
            return current_label
        # Form Validation puede probar opciones reales distintas entre URLs; si
        # no se solicita aleatoriedad se conserva la selección histórica exacta.
        if getattr(getattr(self, "_rotation_config", None), "randomize_academic_selections", False) and kind in {"level", "program"}:
            chosen = secrets.choice(matching or real)
        else:
            chosen = matching[0] if matching else real[0]
        await field.select_option(value=chosen["value"])
        await field.dispatch_event("change")
        await asyncio.sleep(0.35)
        return chosen["text"]

    async def _validate_generic_form(self, form: Any) -> None:
        """Comprueba restricciones HTML y rechazos visibles del validador de la LP."""
        invalid = await form.evaluate(
            """element => {
              const owner = element.matches('form') ? element : element.querySelector('form') || element.closest('form');
              if (!owner) return [];
              const visible = field => field.getClientRects().length && getComputedStyle(field).visibility !== 'hidden';
              const fields = [...owner.querySelectorAll(':invalid, [aria-invalid="true"]')].filter(visible)
                .map(field => field.name || field.id || field.placeholder || field.type);
              // Los validadores externos pueden rechazar datos válidos para HTML.
              // Ignorar mensajes ocultos o informativos evita falsos bloqueos.
              const messages = [...owner.querySelectorAll('[role="alert"]')].filter(visible)
                .map(alert => (alert.innerText || '').trim())
                .filter(text => /error|invalid|incorrect|requerid|required|obligatori|ingresa.*v[aá]lid|enter.*valid/i.test(text));
              return [...new Set([...fields, ...messages])];
            }"""
        )
        if invalid:
            raise UtelQaError(
                "utel_fill",
                "El formulario conserva campos incompletos o rechazados: " + ", ".join(invalid[:8]),
                ':invalid, [aria-invalid="true"], [role="alert"]',
            )

    async def _submit_utel_form(
        self,
        page: Any,
        form: Any,
        should_stop: Callable[[], bool] | None = None,
    ) -> None:
        if not self._is_generic_lp():
            await super()._submit_utel_form(page, form, should_stop)
            return

        await self._validate_generic_form(form)
        submit = form.locator('button[type="submit"], input[type="submit"]')
        rendered_submit = None
        for index in range(await submit.count()):
            candidate = submit.nth(index)
            if await candidate.is_visible() and await self._is_rendered_control(candidate) and not await candidate.is_disabled():
                rendered_submit = candidate
                break
        if rendered_submit is None:
            submit = form.get_by_role(
                "button",
                name=re.compile(r"enviar|solicitar|registr|acceder|contact|send|submit", re.I),
            )
            for index in range(await submit.count()):
                candidate = submit.nth(index)
                if await candidate.is_visible() and await self._is_rendered_control(candidate) and not await candidate.is_disabled():
                    rendered_submit = candidate
                    break
        if rendered_submit is None:
            raise UtelQaError("utel_submit", "El formulario no tiene un botón de envío visible.", 'button[type="submit"]')
        submit = rendered_submit

        self._raise_if_stop_requested(should_stop)
        loop = asyncio.get_running_loop()
        request_future = loop.create_future()
        response_future = loop.create_future()

        def relevant(request: Any) -> bool:
            try:
                if str(request.method).upper() != "POST":
                    return False
                parsed = urlparse(str(request.url))
                return not re.search(r"analytics|doubleclick|facebook|google-analytics|clarity", parsed.netloc, re.I)
            except Exception:
                return False

        def capture_request(request: Any) -> None:
            if relevant(request) and not request_future.done():
                request_future.set_result(request)

        def capture_response(response: Any) -> None:
            if relevant(response.request) and not response_future.done():
                response_future.set_result(response)

        page.on("request", capture_request)
        page.on("response", capture_response)
        try:
            await submit.scroll_into_view_if_needed()
            try:
                await submit.click(force=True, timeout=12000)
            except Exception as error:
                # Algunos contenedores Chakra mantienen el botón fuera del
                # viewport lógico aunque sea el botón visible. El click nativo
                # conserva sus handlers y evita perder el envío por geometría.
                if "outside of the viewport" not in str(error).lower():
                    raise
                await submit.evaluate(
                    "element => { element.scrollIntoView({block: 'center', inline: 'nearest'}); element.click(); }"
                )
            deadline = perf_counter() + 20
            while not request_future.done() and perf_counter() < deadline:
                self._raise_if_stop_requested(should_stop)
                await asyncio.sleep(0.2)
            if not request_future.done():
                raise UtelQaError(
                    "utel_submit",
                    "El botón fue accionado, pero la página no generó una solicitud POST. "
                    "No se buscará un lead que no fue enviado.",
                    'button[type="submit"]',
                )
            self._submission_attempted = True

            deadline = perf_counter() + 45
            while not response_future.done() and perf_counter() < deadline:
                self._raise_if_stop_requested(should_stop)
                await asyncio.sleep(0.2)
            if not response_future.done():
                raise UnconfirmedSubmission(
                    "utel_submit",
                    "Se observó el POST del formulario, pero no llegó una respuesta concluyente. "
                    "Se verificará el CRM sin reenviar.",
                )
            response = response_future.result()
            status = int(getattr(response, "status", 0) or 0)
            if 200 <= status < 400:
                return
            # Las LP genéricas también pueden registrar el lead antes de un 5xx.
            if status >= 500 or status == 0:
                raise UnconfirmedSubmission(
                    "utel_submit",
                    f"La landing respondió HTTP {status or 'desconocido'} después del POST. "
                    "Se verificará el mismo lead en CRM sin reenviar.",
                )
            raise RejectedSubmission(
                "utel_submit",
                f"La landing rechazó el envío con HTTP {status}. No se consultará CRM.",
            )
        finally:
            if not request_future.done():
                request_future.cancel()
            if not response_future.done():
                response_future.cancel()
            with suppress(Exception):
                page.remove_listener("request", capture_request)
            with suppress(Exception):
                page.remove_listener("response", capture_response)
