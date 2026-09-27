"""Captura los valores visibles de un formulario QA antes de enviarlo."""

from __future__ import annotations

from typing import Any


async def capture_visible_form_fields(form: Any) -> list[dict[str, str]]:
    """Lee controles visibles sin incluir secretos, tokens ni campos ocultos.

    La lectura se hace en el contexto del propio formulario para que funcione
    también con landings embebidas en un iframe. No provoca eventos ni envíos.
    """

    return await form.locator("input, select, textarea").evaluate_all(
        """elements => elements.flatMap((element, index) => {
          const type = (element.type || element.tagName || '').toLowerCase();
          if (['hidden', 'password', 'file', 'submit', 'button', 'reset'].includes(type)) return [];
          const bounds = element.getBoundingClientRect();
          const style = getComputedStyle(element);
          if (!bounds.width || !bounds.height || style.visibility === 'hidden' || style.display === 'none') return [];
          if (type === 'radio' && !element.checked) return [];

          // El texto del selector es lo que la persona ve; su value interno
          // puede ser un código opaco y no sirve para auditar el formulario.
          const selected = element.tagName === 'SELECT'
            ? [...element.selectedOptions].map(option => option.textContent.trim()).join(', ')
            : null;
          const value = type === 'checkbox'
            ? (element.checked ? 'Sí' : 'No')
            : (selected === null ? String(element.value || '') : selected);
          const label = [...(element.labels || [])]
            .map(item => item.textContent.trim()).find(Boolean)
            || element.getAttribute('aria-label')
            || element.getAttribute('placeholder')
            || element.getAttribute('data-cy')
            || element.name || element.id || `Campo ${index + 1}`;
          return [{
            key: String(element.name || element.id || label).trim().slice(0, 120),
            label: String(label).replace(/\\s+/g, ' ').trim().slice(0, 120),
            type,
            value: String(value).trim().slice(0, 1000),
          }];
        })"""
    )
