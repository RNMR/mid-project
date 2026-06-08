"""
generator.py
============
Paso 2  – Modelo de embeddings: BAAI/bge-small-en-v1.5 (open-source, BGE).
Paso 8  – Generación de embeddings en batch + optimización.

Justificación del modelo (assignment Step 2):
  - BAAI/bge-small-en-v1.5: 384 dimensiones, buen rendimiento en textos técnicos
    español/inglés, costo cero de inferencia (local), permite migración a
    BGE-large o Instructor sin cambiar la interfaz
  - Batch inference (EMBEDDING_BATCH=32): maximiza throughput GPU/CPU
  - En producción: escalar con Azure OpenAI ada-002 o AWS Titan
    si se requieren garantías de SLA > 99.9% (Paso 10)
"""

from __future__ import annotations

import logging

import numpy as np
from tqdm import tqdm

from config.settings import EMBEDDING_BATCH, EMBEDDING_MODEL

logger = logging.getLogger(__name__)


class EmbeddingGenerator:
    """Genera embeddings densos usando sentence-transformers (BGE).

    Paso 8 – Generación en batch + evaluación de latencia.
    """

    def __init__(self, model_name: str = EMBEDDING_MODEL):
        self._model_name = model_name
        self._model = None  # lazy load para no penalizar el import del pipeline

    def _ensure_loaded(self) -> None:
        if self._model is None:
            logger.info(f"Cargando modelo de embeddings: {self._model_name}")
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(self._model_name)
            logger.info(f"Modelo listo – dimensión: {self._model.get_sentence_embedding_dimension()}")

    def encode(self, texts: list[str]) -> list[list[float]]:
        """Genera embeddings para una lista de textos.

        Retorna lista de vectores float32 (lista de listas para ChromaDB).
        """
        self._ensure_loaded()
        all_embeddings: list[np.ndarray] = []

        batches = [texts[i: i + EMBEDDING_BATCH] for i in range(0, len(texts), EMBEDDING_BATCH)]
        for batch in tqdm(batches, desc="Generando embeddings", unit="batch", leave=False):
            vecs = self._model.encode(
                batch,
                convert_to_numpy=True,
                show_progress_bar=False,
                normalize_embeddings=True,  # normalización L2 → cosine similarity
            )
            all_embeddings.extend(vecs)

        # ChromaDB espera list[list[float]]
        return [vec.tolist() for vec in all_embeddings]

    @property
    def dimension(self) -> int:
        self._ensure_loaded()
        return self._model.get_sentence_embedding_dimension()
