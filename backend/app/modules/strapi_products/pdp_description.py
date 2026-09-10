from __future__ import annotations

import re
import unicodedata
from io import BytesIO
from pathlib import Path
from urllib.parse import urlparse

from docx import Document
from pypdf import PdfReader


def _normalize(value: str) -> str:
    plain = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    return " ".join(re.sub(r"[^a-z0-9 ]+", " ", plain.casefold()).split())


def _clean(value: str) -> str:
    return " ".join(value.replace("\u00a0", " ").split()).strip()


def _is_heading(text: str) -> bool:
    return len(text) <= 140 and (text.isupper() or re.match(r"^(?:\d+[.)]?|perfil|plan de estudios|competencias|informacion)\b", text, re.I))


def _extract_after_title(program: str, blocks: list[str], source: str) -> str:
    target = _normalize(program)
    title_index = next((index for index, block in enumerate(blocks) if _normalize(block) == target or target in _normalize(block)), None)
    if title_index is None:
        raise ValueError(f"No se encontro el titulo del programa en {source}.")

    for candidate in blocks[title_index + 1:]:
        text = _clean(candidate)
        if not text:
            continue
        if _is_heading(text):
            raise ValueError(f"No se encontro una descripcion debajo del titulo en {source}.")
        return text
    raise ValueError(f"No se encontro una descripcion debajo del titulo en {source}.")


def extract_description(program: str, filename: str, content: bytes) -> str:
    extension = Path(urlparse(filename).path or filename).suffix.casefold()
    try:
        if extension == ".docx":
            document = Document(BytesIO(content))
            blocks = [paragraph.text for paragraph in document.paragraphs]
            return _extract_after_title(program, blocks, filename)
        if extension == ".pdf":
            reader = PdfReader(BytesIO(content))
            blocks = []
            for page in reader.pages:
                blocks.extend((page.extract_text() or "").splitlines())
            return _extract_after_title(program, blocks, filename)
    except ValueError:
        raise
    except Exception as error:
        raise ValueError(f"No se pudo abrir el Documento PDP {filename}.") from error
    raise ValueError(f"Formato de Documento PDP no soportado: {filename}.")

