"""
base_extractor.py
=================
Paso 7 – Pipeline de Ingesta: tipos de datos comunes para todos los extractores.

Define los contratos de datos que fluyen por el pipeline ETL:
  ExtractedPage      → unidad mínima de texto (página PDF o lote de filas CSV)
  ExtractedDocument  → documento completo con páginas y metadatos de origen
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ExtractedPage:
    """Unidad mínima de texto extraído de un documento."""
    page_num: int           # número de página (PDFs) o índice de lote (CSVs)
    text: str               # texto limpio extraído
    extra: dict = field(default_factory=dict)  # metadatos adicionales por extractor


@dataclass
class ExtractedDocument:
    """Documento completo extraído desde una fuente.

    Es la salida de cualquier extractor y la entrada al transformador (cleaner/chunker).
    """
    source_file: str        # nombre del archivo (sin ruta completa)
    source_path: str        # ruta absoluta
    domain: str             # dominio asignado: legal | technical | infrastructure | operations
    shard: str              # nombre del shard ChromaDB destino
    file_type: str          # ".pdf" | ".csv"
    pages: list[ExtractedPage] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)

    @property
    def full_text(self) -> str:
        return "\n\n".join(p.text for p in self.pages if p.text.strip())

    @property
    def total_chars(self) -> int:
        return sum(len(p.text) for p in self.pages)

    def doc_id(self) -> str:
        """ID determinístico basado en nombre de archivo."""
        return Path(self.source_file).stem.replace(" ", "_").lower()[:64]
