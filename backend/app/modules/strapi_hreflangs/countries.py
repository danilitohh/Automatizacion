"""Destinos URL y reglas de slug que usa la sincronización de hreflangs."""

from dataclasses import dataclass
import re
from urllib.parse import quote


@dataclass(frozen=True)
class CountryTarget:
    """Describe el locale hreflang y la ruta pública de un país."""

    hreflang: str
    base_url: str
    country_path: str | None = None


TARGETS = (
    CountryTarget("x-default", "https://utel.edu.mx"),
    CountryTarget("es-mx", "https://utel.edu.mx"),
    CountryTarget("es-co", "https://utel.edu.mx", "colombia"),
    CountryTarget("es-pe", "https://utlenlinea.com"),
    CountryTarget("es-ec", "https://utel.edu.mx", "ecuador"),
    CountryTarget("es-us", "https://utel.edu.mx", "usa"),
    CountryTarget("es-ar", "https://utel.edu.mx", "argentina"),
    CountryTarget("es-do", "https://utel.edu.mx", "dominicana"),
    CountryTarget("es-gt", "https://utel.edu.mx", "guatemala"),
    CountryTarget("es-cl", "https://utel.edu.mx", "chile"),
    CountryTarget("es-sv", "https://utel.edu.mx", "elsalvador"),
    CountryTarget("es-bo", "https://utel.edu.mx", "bolivia"),
    CountryTarget("es-pa", "https://utel.edu.mx", "panama"),
    CountryTarget("es-py", "https://utel.edu.mx", "paraguay"),
)
COUNTRY_TARGETS = tuple(target for target in TARGETS if target.hreflang.startswith("es-"))
LOCALES = tuple(target.hreflang for target in COUNTRY_TARGETS)
CAREER_LOCALES = {"es-cl", "es-bo", "es-co", "es-ec", "es-py", "es-pe"}
MAX_HREFLANGS = 14


def build_url(target: CountryTarget, slug: str) -> str:
    """Construye la URL pública, adaptando los prefijos de carrera por país."""

    localized_slug = slug
    if target.hreflang in CAREER_LOCALES and re.match(r"^licenciatura(?=-|$)", localized_slug, re.IGNORECASE):
        localized_slug = "carrera" + localized_slug[len("licenciatura"):]
    elif target.hreflang not in CAREER_LOCALES and re.match(r"^carrera(?=-|$)", localized_slug, re.IGNORECASE):
        localized_slug = "licenciatura" + localized_slug[len("carrera"):]
    if target.hreflang == "es-cl" and re.match(r"^maestria(?=-|$)", localized_slug, re.IGNORECASE):
        localized_slug = "magister" + localized_slug[len("maestria"):]
    elif target.hreflang != "es-cl" and re.match(r"^magister(?=-|$)", localized_slug, re.IGNORECASE):
        localized_slug = "maestria" + localized_slug[len("magister"):]

    parts = [target.base_url.rstrip("/")]
    if target.country_path:
        parts.append(quote(target.country_path, safe=""))
    parts.append(quote(localized_slug.strip("/"), safe="-._~"))
    return "/".join(parts)


def create_hreflang(code: str, url: str) -> dict[str, str]:
    """Crea un elemento con el formato del componente MultipleHrefLangs."""

    return {"hrefLang": code, "url": url, "locale": "", "rel": "alternate"}
