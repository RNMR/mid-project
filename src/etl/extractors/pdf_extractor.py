"""
pdf_extractor.py
================
Paso 7 – Extracción: lee PDFs y retorna texto por página.

Soporta:
  - PDFs con texto embebido (pdfplumber)
  - Detección de PDFs escaneados (advertencia + skip)
  - Limpieza básica de headers/footers repetitivos

Documentos procesados:
  LEGAL/         → shard_legal     (Ley N° 31557)
  MANUALES/      → shard_technical (lineamientos GTI, AWS, DynamoDB, Terraform, Git)
  DOC WEB/       → shard_infrastructure (Docker, Kubernetes, AWS Well-Architected)
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

import pdfplumber

from .base_extractor import ExtractedDocument, ExtractedPage

logger = logging.getLogger(__name__)

# Umbral de texto mínimo por página para no considerarla "escaneada/vacía"
_MIN_PAGE_CHARS = 50

# Patrones de ruido común en PDFs (pies de página, numeración, marcas de agua)
_NOISE_PATTERNS = [
    re.compile(r"^\s*\d+\s*$"),                     # número de página solo
    re.compile(r"(?i)^confidential\s*$"),
    re.compile(r"(?i)^www\.[^\s]+\s*$"),             # URLs de pie de página
    re.compile(r"^[─═─\-]{5,}\s*$"),                 # líneas horizontales
]


def _is_noise_line(line: str) -> bool:
    return any(p.match(line.strip()) for p in _NOISE_PATTERNS)


class PDFExtractor:
    """Extrae texto de archivos PDF página por página.

    Paso 7 – Limpieza: elimina líneas de ruido (headers/footers repetitivos).
    """

    def extract(self, pdf_path: Path, domain: str, shard: str) -> ExtractedDocument:
        logger.info(f"Extrayendo PDF: {pdf_path.name} → dominio={domain}")

        pages: list[ExtractedPage] = []
        scanned_pages = 0

        try:
            with pdfplumber.open(pdf_path) as pdf:
                total_pages = len(pdf.pages)
                for page_num, page in enumerate(pdf.pages, start=1):
                    raw_text = page.extract_text() or ""
                    cleaned = self._clean_page(raw_text)

                    if len(cleaned) < _MIN_PAGE_CHARS:
                        scanned_pages += 1
                        continue

                    pages.append(ExtractedPage(
                        page_num=page_num,
                        text=cleaned,
                        extra={"pdf_total_pages": total_pages},
                    ))
        except Exception as exc:
            logger.error(f"Error leyendo {pdf_path.name}: {exc}")
            raise

        if scanned_pages:
            logger.warning(
                f"{pdf_path.name}: {scanned_pages} páginas sin texto detectable "
                f"(posible contenido escaneado – se requeriría OCR para procesarlas)"
            )

        logger.info(f"  → {len(pages)} páginas extraídas de {pdf_path.name}")

        return ExtractedDocument(
            source_file=pdf_path.name,
            source_path=str(pdf_path),
            domain=domain,
            shard=shard,
            file_type=".pdf",
            pages=pages,
            metadata={
                "total_pdf_pages": len(pages) + scanned_pages,
                "readable_pages": len(pages),
                "scanned_pages": scanned_pages,
            },
        )

    def _clean_page(self, raw: str) -> str:
        """Elimina líneas de ruido y normaliza espacios."""
        lines = raw.splitlines()
        cleaned_lines = [ln for ln in lines if not _is_noise_line(ln)]
        text = "\n".join(cleaned_lines)
        # Colapsa múltiples líneas en blanco a máximo 2
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()
