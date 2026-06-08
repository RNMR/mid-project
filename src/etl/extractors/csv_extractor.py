"""
csv_extractor.py
================
Paso 7 – Extracción: lee CSVs de encuestas Qualtrics y los convierte a texto.

Formato Qualtrics (3 filas de cabecera):
  Fila 0: códigos internos en inglés  (StartDate, Q1, Q2 …)
  Fila 1: etiquetas legibles en español
  Fila 2: ImportId JSON  ({"ImportId":"startDate"} …)
  Fila 3+: respuestas reales

Paso 7 – Chunking operacional: se agrupa cada CSV_ROWS_PER_CHUNK filas
en un chunk de texto para que el contexto de cada shard sea coherente.

Documentos procesados:
  ENCUESTAS/ → shard_operations
    - Apuestas deportivas – CES
    - Juegos Casino – CES
    - Millón City 2026 – Mensual
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

import pandas as pd

from config.settings import CSV_ROWS_PER_CHUNK
from .base_extractor import ExtractedDocument, ExtractedPage

logger = logging.getLogger(__name__)

# Columnas que contienen PII o metadatos irrelevantes para el RAG
# Paso 1 – Regla de negocio: datos anonimizados en el vector store
_EXCLUDE_COLS = {
    "RecipientLastName", "RecipientFirstName", "RecipientEmail",
    "Apellido del destinatario", "Nombre del destinatario",
    "Correo electrónico del destinatario",
    "IPAddress", "Dirección IP",
    "LocationLatitude", "LocationLongitude",
    "Latitud de la ubicación", "Longitud de la ubicación",
    "ExternalReference", "Referencia a datos externos",
    "ResponseId", "ID de respuesta",
}

# Columnas de análisis AI ya procesadas (redundantes con el texto original)
_REDUNDANT_COLS_PATTERN = re.compile(
    r"(ImportId|QID\d+_AI|bmr1gics|surveyversionid|DistributionChannel|UserLanguage)"
)


class CSVExtractor:
    """Extrae y estructura CSVs de encuestas Qualtrics en texto legible para RAG."""

    def extract(self, csv_path: Path, domain: str, shard: str) -> ExtractedDocument:
        logger.info(f"Extrayendo CSV: {csv_path.name} → dominio={domain}")

        df = self._load_qualtrics_csv(csv_path)
        df = self._drop_pii_and_noise(df)

        survey_name = self._infer_survey_name(csv_path.name)
        pages = self._to_pages(df, survey_name)

        logger.info(f"  → {len(df)} respuestas → {len(pages)} chunks desde {csv_path.name}")

        return ExtractedDocument(
            source_file=csv_path.name,
            source_path=str(csv_path),
            domain=domain,
            shard=shard,
            file_type=".csv",
            pages=pages,
            metadata={
                "total_rows": len(df),
                "columns": list(df.columns),
                "survey_name": survey_name,
            },
        )

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _load_qualtrics_csv(self, path: Path) -> pd.DataFrame:
        """Carga el CSV respetando el formato de 3 cabeceras de Qualtrics."""
        raw = pd.read_csv(path, header=None, dtype=str, low_memory=False)

        # Fila 1 contiene las etiquetas legibles en español
        spanish_labels = raw.iloc[1].fillna("").tolist()

        # Datos reales empiezan en fila 3
        data = raw.iloc[3:].copy()
        data.columns = spanish_labels
        return data.reset_index(drop=True)

    def _drop_pii_and_noise(self, df: pd.DataFrame) -> pd.DataFrame:
        cols_to_drop = [
            c for c in df.columns
            if c in _EXCLUDE_COLS or _REDUNDANT_COLS_PATTERN.search(str(c))
        ]
        return df.drop(columns=cols_to_drop, errors="ignore")

    def _infer_survey_name(self, filename: str) -> str:
        """Extrae el nombre de la encuesta desde el nombre de archivo."""
        name = re.sub(r"_\d{2} de \w+ de \d{4}_.*$", "", filename)
        name = re.sub(r"[-_]+", " ", name).strip()
        return name.replace(".csv", "")

    def _to_pages(self, df: pd.DataFrame, survey_name: str) -> list[ExtractedPage]:
        """Convierte grupos de filas en páginas de texto para el chunker."""
        pages: list[ExtractedPage] = []
        chunk_size = CSV_ROWS_PER_CHUNK

        for batch_idx, start in enumerate(range(0, len(df), chunk_size)):
            batch = df.iloc[start: start + chunk_size]
            text = self._batch_to_text(batch, survey_name, start)
            if text.strip():
                pages.append(ExtractedPage(
                    page_num=batch_idx,
                    text=text,
                    extra={"row_start": start, "row_end": start + len(batch)},
                ))

        return pages

    def _batch_to_text(self, batch: pd.DataFrame, survey_name: str, row_offset: int) -> str:
        """Convierte un lote de filas a texto estructurado legible."""
        lines = [f"Encuesta: {survey_name}", ""]

        for i, (_, row) in enumerate(batch.iterrows(), start=row_offset + 1):
            lines.append(f"── Respuesta #{i} ──")
            for col, val in row.items():
                val_str = str(val).strip()
                if val_str and val_str not in ("nan", "None", ""):
                    col_str = str(col).strip()
                    if col_str:
                        lines.append(f"  {col_str}: {val_str}")
            lines.append("")

        return "\n".join(lines)
