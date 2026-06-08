"""
chunker.py
==========
Paso 7 – Chunking: divide documentos en fragmentos óptimos para embedding.

Estrategias implementadas (assignment Step 7):
  1. SectionChunker     – detecta cabeceras de sección (semántico / por secciones)
  2. SlidingWindowChunker – ventana deslizante con overlap (token-based dinámico)
  3. SmartChunker       – usa SectionChunker primero; cae en SlidingWindow si
                          no detecta estructura de secciones

Justificación de método:
  - Documentos técnicos y legales tienen secciones explícitas → SectionChunker
    preserva la coherencia semántica y reduce el ruido cross-sección
  - Para PDFs sin estructura clara (p.ej. tablas densas) → SlidingWindow
    garantiza que ningún chunk supere el límite de tokens del modelo
  - CSVs ya llegan pre-chunkeados por CSVExtractor (grupos de filas)
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field

from config.settings import CHUNK_OVERLAP_TOKENS, CHUNK_SIZE_TOKENS, MIN_CHUNK_TOKENS
from src.etl.extractors.base_extractor import ExtractedDocument

# ── Tipos ─────────────────────────────────────────────────────────────────────


@dataclass
class DocumentChunk:
    """Un fragmento de texto listo para generar embedding y almacenar en shard."""
    chunk_id: str
    doc_id: str
    domain: str
    shard: str
    text: str
    metadata: dict = field(default_factory=dict)

    def approx_tokens(self) -> int:
        return _word_tokens(self.text)


def _word_tokens(text: str) -> int:
    """Aproximación de tokens: 1 token ≈ 0.75 palabras (multi-language safe)."""
    return max(1, int(len(text.split()) * 4 / 3))


# ── Patrones de sección para español e inglés ─────────────────────────────────
_SECTION_PATTERNS = [
    re.compile(r"^(ARTÍCULO|ARTICULO)\s+\d+", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^(CAPÍTULO|CAPITULO|TÍTULO|TITULO|SECCIÓN|SECCION)\s+[IVX\d]+", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^\d+\.\d*\s+[A-ZÁÉÍÓÚÑ][A-ZÁÉÍÓÚÑA-Za-z\s]{3,}$", re.MULTILINE),  # "1.2 OBJETIVO"
    re.compile(r"^\d+\.\s+[A-ZÁÉÍÓÚÑ][A-ZÁÉÍÓÚÑ\s]{3,}$", re.MULTILINE),            # "1. OBJETIVO"
    re.compile(r"^(Chapter|Section|PART)\s+[\dIVX]+", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^#{1,3}\s+\S", re.MULTILINE),                                          # Markdown headers
]


class SectionChunker:
    """Divide texto en chunks usando cabeceras de sección como delimitadores.

    Paso 7 – Chunking semántico / basado en secciones.
    Cada sección del documento se convierte en uno o más chunks (si es muy larga).
    """

    def __init__(self, max_tokens: int = CHUNK_SIZE_TOKENS):
        self.max_tokens = max_tokens

    def chunk(self, text: str, doc_id: str, domain: str, shard: str,
              base_meta: dict) -> list[DocumentChunk]:
        splits = self._split_by_sections(text)
        if len(splits) <= 1:
            return []  # señal de fallback a SlidingWindow

        chunks: list[DocumentChunk] = []
        for section_title, section_text in splits:
            full_text = f"{section_title}\n{section_text}".strip() if section_title else section_text
            sub = self._split_long_section(full_text, doc_id, domain, shard, base_meta, section_title)
            chunks.extend(sub)
        return chunks

    def _split_by_sections(self, text: str) -> list[tuple[str, str]]:
        """Detecta posiciones de cabeceras y divide el texto entre ellas."""
        positions: list[int] = []
        for pattern in _SECTION_PATTERNS:
            for m in pattern.finditer(text):
                positions.append(m.start())

        if not positions:
            return [(("", text))]

        positions = sorted(set(positions))
        sections: list[tuple[str, str]] = []
        for i, pos in enumerate(positions):
            end = positions[i + 1] if i + 1 < len(positions) else len(text)
            segment = text[pos:end]
            lines = segment.splitlines()
            title = lines[0] if lines else ""
            body = "\n".join(lines[1:]).strip()
            if body:
                sections.append((title, body))

        # Texto antes de la primera sección
        if positions[0] > 0:
            preamble = text[: positions[0]].strip()
            if preamble:
                sections.insert(0, ("", preamble))

        return sections if sections else [("", text)]

    def _split_long_section(self, text: str, doc_id: str, domain: str, shard: str,
                             base_meta: dict, section_title: str) -> list[DocumentChunk]:
        """Si una sección supera max_tokens la divide en ventanas."""
        if _word_tokens(text) <= self.max_tokens:
            return [_make_chunk(text, doc_id, domain, shard, base_meta,
                                extra={"section_title": section_title})]

        sw = SlidingWindowChunker(self.max_tokens)
        return sw.chunk(text, doc_id, domain, shard,
                        {**base_meta, "section_title": section_title})


class SlidingWindowChunker:
    """Divide texto con ventana deslizante de tokens con overlap.

    Paso 7 – Chunking token-based dinámico (fallback / secciones largas).
    """

    def __init__(self, max_tokens: int = CHUNK_SIZE_TOKENS,
                 overlap: int = CHUNK_OVERLAP_TOKENS):
        self.max_tokens = max_tokens
        self.overlap = overlap

    def chunk(self, text: str, doc_id: str, domain: str, shard: str,
              base_meta: dict) -> list[DocumentChunk]:
        words = text.split()
        chunks: list[DocumentChunk] = []
        step = max(1, self.max_tokens - self.overlap)

        start = 0
        while start < len(words):
            end = start + self.max_tokens
            segment = " ".join(words[start:end])
            if _word_tokens(segment) >= MIN_CHUNK_TOKENS:
                chunks.append(_make_chunk(segment, doc_id, domain, shard, base_meta,
                                          extra={"word_start": start, "word_end": end}))
            start += step

        return chunks


class SmartChunker:
    """Orquesta SectionChunker + SlidingWindowChunker.

    Paso 7 – Estrategia de chunking adaptativo:
      1. Intenta SectionChunker (preserva coherencia semántica)
      2. Si no detecta secciones → SlidingWindowChunker (garantía de tamaño)
    """

    def chunk_document(self, doc: ExtractedDocument) -> list[DocumentChunk]:
        all_chunks: list[DocumentChunk] = []
        doc_id = doc.doc_id()
        base_meta = {
            "source_file": doc.source_file,
            "domain": doc.domain,
            "shard": doc.shard,
            "file_type": doc.file_type,
        }

        section_chunker = SectionChunker()
        sliding_chunker = SlidingWindowChunker()

        for page in doc.pages:
            if not page.text.strip():
                continue

            page_meta = {**base_meta, "page_num": page.page_num, **page.extra}

            # CSVs llegan pre-chunkeados → aplicar SlidingWindow solo si exceden límite
            if doc.file_type == ".csv":
                chunks = sliding_chunker.chunk(page.text, doc_id, doc.domain, doc.shard, page_meta)
            else:
                chunks = section_chunker.chunk(page.text, doc_id, doc.domain, doc.shard, page_meta)
                if not chunks:
                    chunks = sliding_chunker.chunk(page.text, doc_id, doc.domain, doc.shard, page_meta)

            all_chunks.extend(chunks)

        return all_chunks


# ── Helper ────────────────────────────────────────────────────────────────────

def _make_chunk(text: str, doc_id: str, domain: str, shard: str,
                base_meta: dict, extra: dict | None = None) -> DocumentChunk:
    chunk_id = f"{doc_id}_{uuid.uuid4().hex[:8]}"
    meta = {**base_meta, "token_approx": _word_tokens(text), **(extra or {})}
    return DocumentChunk(chunk_id=chunk_id, doc_id=doc_id, domain=domain,
                         shard=shard, text=text, metadata=meta)
