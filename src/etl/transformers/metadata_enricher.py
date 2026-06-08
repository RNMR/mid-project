"""
metadata_enricher.py
====================
Paso 7 – Extracción de metadatos: enriquece cada chunk antes de indexarlo.

Metadatos añadidos:
  - ingested_at   : timestamp ISO de ingesta
  - chunk_index   : posición en el documento
  - total_chunks  : total de chunks del documento
  - language_hint : español o inglés (heurística)

Estos metadatos permiten filtrado por shard y faceting en Paso 3 (Domain Router)
y son esenciales para la observabilidad en Paso 11.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

from src.etl.transformers.chunker import DocumentChunk

_SPANISH_INDICATORS = re.compile(
    r"\b(el|la|los|las|que|por|con|para|una|del|artículo|lineamiento|ley)\b",
    re.IGNORECASE,
)


def _detect_language(text: str) -> str:
    sample = text[:300]
    spanish_hits = len(_SPANISH_INDICATORS.findall(sample))
    return "es" if spanish_hits >= 3 else "en"


class MetadataEnricher:
    """Añade metadatos de contexto a cada chunk para facilitar retrieval y filtrado.

    Paso 7 – Extracción de metadatos.
    Paso 11 – Observabilidad: los metadatos se usan en dashboards de Grafana/RAGAS.
    """

    def enrich(self, chunks: list[DocumentChunk]) -> list[DocumentChunk]:
        now = datetime.now(timezone.utc).isoformat()
        total = len(chunks)

        for idx, chunk in enumerate(chunks):
            chunk.metadata.update({
                "chunk_index": idx,
                "total_chunks_in_doc": total,
                "ingested_at": now,
                "language_hint": _detect_language(chunk.text),
                "char_count": len(chunk.text),
            })

        return chunks
