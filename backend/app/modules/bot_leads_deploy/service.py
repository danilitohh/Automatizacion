"""Resolución de país/nivel y catálogo para Bot Leads Deploy.

Este archivo contiene únicamente ajustes propios de Leads Deploy. No modifica
el comportamiento del Bot de nuevos productos.
"""

from __future__ import annotations

from pathlib import Path

from .spreadsheet_service import LeadsDeploySpreadsheetService as BaseLeadsDeploySpreadsheetService


class LeadsDeploySpreadsheetService(BaseLeadsDeploySpreadsheetService):
    """Capa final del parser/catálogo usada por la API de Leads Deploy."""

    GLOBAL_COUNTRY_HINTS = (
        (("filipinas", "philippines"), "Filipinas"),
        (("india",), "India"),
        (("indonesia",), "Indonesia"),
    )

    @classmethod
    def effective_country(cls, country: str, level: str, url: str) -> str:
        """Resuelve filas Global usando el país embebido en Nivel cuando existe.

        La matriz Leads Deploy agrupa algunos mercados internacionales bajo
        ``Global`` y distingue el país dentro de Nivel (por ejemplo,
        ``India Bachelor``). El servicio base solo resolvía Filipinas; por eso
        India/Indonesia podían terminar buscando programas para ``Global`` y
        dejar ``utel_url`` vacío.
        """

        if cls._normalize(country) != "global":
            return super().effective_country(country, level, url)

        source = cls._normalize(f"{level} {url}")
        for aliases, resolved_country in cls.GLOBAL_COUNTRY_HINTS:
            if any(alias in source for alias in aliases):
                return resolved_country

        return super().effective_country(country, level, url)

    @classmethod
    def deploy_navigation_plan(cls, raw_level: str, country: str) -> dict[str, str]:
        """Interpreta Bachelor/Master en portales internacionales."""

        level = cls._normalize(raw_level)
        country_key = cls._catalog_key(country)
        international = country_key in {
            "filipinas",
            "india",
            "indonesia",
            "global",
        }

        if international and ("master" in level or "maestr" in level):
            return {
                "modality": "Online",
                "level": "Master's Degree",
                "navigation_modality": "",
                "navigation_level": "Master",
                "navigation_sublevel": "",
            }

        if international and ("bachelor" in level or "licenc" in level):
            return {
                "modality": "Online",
                "level": "Bachelor's Degree",
                "navigation_modality": "",
                "navigation_level": "Bachelor",
                "navigation_sublevel": "",
            }

        return super().deploy_navigation_plan(raw_level, country)

    def choose_catalog_program(
        self,
        country: str,
        level: str,
        modality: str,
        database_path: Path,
    ) -> dict[str, str]:
        """Garantiza una URL de catálogo antes de construir ``UtelQaConfig``.

        Se prueban primero los valores originales y luego el nivel normalizado
        por el plan de navegación. Si no existe una coincidencia real en el
        catálogo, se devuelve un error de negocio legible en vez del error
        genérico de Pydantic por ``utel_url=''``.
        """

        candidate = super().choose_catalog_program(
            country,
            level,
            modality,
            database_path,
        )
        if candidate is not None:
            return candidate

        navigation = self.deploy_navigation_plan(level, country)
        alternate_level = navigation.get("level", "")
        alternate_modality = navigation.get("modality", "")

        if (
            self._catalog_level_key(alternate_level)
            != self._catalog_level_key(level)
            or self._catalog_modality_key(alternate_modality)
            != self._catalog_modality_key(modality)
        ):
            candidate = super().choose_catalog_program(
                country,
                alternate_level,
                alternate_modality,
                database_path,
            )
            if candidate is not None:
                return candidate

        raise ValueError(
            "Leads Deploy no encontró un programa con URL en el catálogo interno "
            f"para País='{country}', Nivel='{level}', Modalidad='{modality}'. "
            "Revisa esa combinación en backend/data/utel_programas1.xlsx."
        )
