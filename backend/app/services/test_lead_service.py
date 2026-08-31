"""Generación persistente de datos sintéticos para pruebas de leads."""

import re
import unicodedata
from datetime import date, datetime
from pathlib import Path
from typing import Any

from ..database.connection import get_connection, initialize_database


class TestLeadService:
    """Reserva emails y teléfonos únicos sin usar datos de personas reales."""

    __test__ = False

    # Prefijo nacional y cantidad total de dígitos del teléfono que espera el formulario.
    PHONE_FORMATS = {
        "mexico": ("55", 10),
        "ecuador": ("9", 9),
        "colombia": ("3", 10),
        "peru": ("9", 9),
        "chile": ("9", 9),
        "argentina": ("9", 10),
        "usa": ("20255501", 10),
        "united states": ("20255501", 10),
        "bolivia": ("6", 8),
        "paraguay": ("9", 9),
        "dominicana": ("80955501", 10),
        "republica dominicana": ("80955501", 10),
        "guatemala": ("5", 8),
        "panama": ("6", 8),
        "el salvador": ("7", 8),
        "global": ("20255501", 10),
        "filipinas": ("9", 10),
        "india": ("9", 10),
    }

    def __init__(self, database_path: Path):
        self.database_path = database_path
        initialize_database(database_path)

    def reserve(self, country: str) -> dict[str, Any]:
        normalized_country = self._normalize(country)
        prefix, total_digits = self.PHONE_FORMATS.get(normalized_country, ("9", 10))
        today = date.today().isoformat()
        country_label = country.strip()

        with get_connection(self.database_path) as connection:
            # BEGIN IMMEDIATE evita que dos ejecuciones simultáneas reciban el mismo N.
            connection.execute("BEGIN IMMEDIATE")
            next_sequence = connection.execute(
                "SELECT COALESCE(MAX(sequence), 0) + 1 FROM test_leads WHERE test_date = ?",
                (today,),
            ).fetchone()[0]
            phone_sequence = connection.execute(
                "SELECT COALESCE(MAX(id), 0) + 1 FROM test_leads"
            ).fetchone()[0]
            email = f"Testing{today}N{next_sequence}@testingUtel.com"
            suffix_digits = total_digits - len(prefix)
            capacity = 10 ** suffix_digits
            used = {row[0] for row in connection.execute(
                "SELECT phone FROM test_leads WHERE phone LIKE ?", (prefix + "%",)
            )}
            # Nunca truncar el prefijo ni reciclar un telefono ya reservado.
            candidate = phone_sequence if phone_sequence < capacity else 0
            for _ in range(len(used) + 1):
                phone = prefix + str(candidate).zfill(suffix_digits)
                if phone not in used:
                    break
                candidate = (candidate + 1) % capacity
            else:
                raise ValueError(f"Se agotaron los telefonos de prueba para {country_label}; configure un rango QA autorizado.")
            name = f"Danilo{phone_sequence}"
            connection.execute(
                "INSERT INTO test_leads (test_date, sequence, country, email, phone, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (today, next_sequence, country_label, email, phone, datetime.now().isoformat(timespec="seconds")),
            )

        return {"name": name, "email": email, "phone": phone, "country": country_label, "sequence": next_sequence}

    @staticmethod
    def _normalize(value: str) -> str:
        value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii").lower()
        return re.sub(r"\s+", " ", value).strip()
