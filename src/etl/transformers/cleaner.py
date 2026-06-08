"""
cleaner.py
==========
Paso 7 – Limpieza y normalización de texto extraído.

Aplica:
  - Normalización unicode (NFC)
  - Eliminación de caracteres de control
  - Colapso de espacios múltiples
  - Normalización de saltos de línea
  - Detección de idioma para logging (heurística simple)
"""

from __future__ import annotations

import re
import unicodedata

from src.etl.extractors.base_extractor import ExtractedDocument, ExtractedPage


class TextCleaner:
    """Limpia y normaliza texto antes del chunking.

    Paso 7 – Normalización: prepara el texto para que los embeddings
    sean consistentes entre documentos de distintos dominios.
    """

    def clean(self, doc: ExtractedDocument) -> ExtractedDocument:
        cleaned_pages = [
            ExtractedPage(
                page_num=p.page_num,
                text=self._clean_text(p.text),
                extra=p.extra,
            )
            for p in doc.pages
        ]
        doc.pages = [p for p in cleaned_pages if len(p.text) >= 20]
        return doc

    def _clean_text(self, text: str) -> str:
        # Normalización Unicode → forma compuesta canónica
        text = unicodedata.normalize("NFC", text)
        # Eliminar caracteres de control excepto \n y \t
        text = re.sub(r"[\x00-\x08\x0b-\x0c\x0e-\x1f\x7f]", "", text)
        # Colapsar espacios múltiples en una línea
        text = re.sub(r"[ \t]{2,}", " ", text)
        # Colapsar más de 2 saltos de línea consecutivos
        text = re.sub(r"\n{3,}", "\n\n", text)
        # Quitar espacios al inicio/fin de cada línea
        lines = [ln.rstrip() for ln in text.splitlines()]
        return "\n".join(lines).strip()
