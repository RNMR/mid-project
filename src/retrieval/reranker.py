"""
reranker.py
===========
Paso 9 – Re-ranking avanzado: cross-encoder + (opcional) LLM-based reranking.

Modelos de re-ranking (assignment Step 9):
  - Cross-encoder: cross-encoder/ms-marco-MiniLM-L-6-v2 (local, open-source)
  - LLM-based: usar Claude para puntuar relevancia (mayor calidad, mayor costo)
  - Fusion ranking (RRF): combinar múltiples shards sin re-ranking costoso

Experimentos comparativos requeridos (Paso 9):
  - Sin reranking vs cross-encoder vs LLM-based: medir MRR@K y NDCG@K
  - Reranking Quality Score (Paso 1 KPI)

TODO – Implementar:
  1. Cargar cross-encoder con sentence-transformers
  2. Puntuar (query, passage) pares
  3. Ordenar por score descendente
  4. Opcional: Reciprocal Rank Fusion para resultados de múltiples shards
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class RetrievedChunk:
    chunk_id: str
    text: str
    metadata: dict
    score: float
    shard: str


class Reranker:
    """Re-ordena resultados de retrieval usando cross-encoder.

    Paso 9 – Re-ranking avanzado: cross-encoder ms-marco-MiniLM-L-6-v2.
    El cross-encoder evalúa cada par (query, chunk) conjuntamente — mayor
    calidad que bi-encoder porque captura interacción entre los dos textos.
    """

    def __init__(self):
        self._model = None  # lazy load al primer uso

    def _ensure_loaded(self) -> None:
        if self._model is not None:
            return
        try:
            from sentence_transformers import CrossEncoder
            from config.settings import RERANKER_MODEL
            logger.info(f"Cargando cross-encoder: {RERANKER_MODEL}")
            self._model = CrossEncoder(RERANKER_MODEL)
            logger.info("Cross-encoder listo")
        except Exception as exc:
            logger.warning(f"Reranker: no se pudo cargar el modelo ({exc}). "
                           "Usando ordenamiento por score original.")

    def rerank(self, query: str, chunks: list[RetrievedChunk],
               top_k: int = 3) -> list[RetrievedChunk]:
        """Re-ordena chunks por relevancia respecto a la query.

        Con cross-encoder: evalúa pares (query, chunk) y ordena por score.
        Sin cross-encoder (fallback): ordena por distancia coseno original.
        """
        self._ensure_loaded()

        if self._model is None:
            # Fallback: distancia coseno (menor = más relevante)
            return sorted(chunks, key=lambda c: c.score)[:top_k]

        # Cross-encoder: puntúa cada par (query, chunk) — score más alto = más relevante
        pairs = [(query, c.text) for c in chunks]
        scores = self._model.predict(pairs, show_progress_bar=False)

        for chunk, score in zip(chunks, scores):
            chunk.score = float(score)

        reranked = sorted(chunks, key=lambda c: c.score, reverse=True)[:top_k]
        logger.info(f"[RERANKER] cross-encoder scores: "
                    + ", ".join(f"{c.score:.3f}" for c in reranked))
        return reranked


def reciprocal_rank_fusion(ranked_lists: list[list[RetrievedChunk]],
                           k: int = 60) -> list[RetrievedChunk]:
    """Fusión de rankings de múltiples shards usando Reciprocal Rank Fusion.

    Paso 9 – Fusion ranking (opcional).
    Útil cuando se consultan múltiples shards en paralelo (Paso 3 multi-index).

    RRF score = Σ 1/(k + rank_i)  para cada lista i donde aparece el chunk.
    """
    rrf_scores: dict[str, float] = {}
    chunk_map: dict[str, RetrievedChunk] = {}

    for ranked in ranked_lists:
        for rank, chunk in enumerate(ranked, start=1):
            rrf_scores[chunk.chunk_id] = rrf_scores.get(chunk.chunk_id, 0.0) + 1.0 / (k + rank)
            chunk_map[chunk.chunk_id] = chunk

    merged = sorted(chunk_map.values(), key=lambda c: rrf_scores[c.chunk_id], reverse=True)
    for chunk in merged:
        chunk.score = rrf_scores[chunk.chunk_id]
    return merged
