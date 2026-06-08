"""
vector_loader.py
================
Paso 8 – Generación de embeddings + carga en shard correspondiente.

Orquesta:
  EmbeddingGenerator → genera vectores BGE en batch
  ShardedVectorStore → almacena en la colección ChromaDB del dominio

En producción (Paso 8):
  - Reemplazar EmbeddingGenerator local con llamada a Azure OpenAI / AWS Titan
  - Reemplazar ShardedVectorStore con cliente Pinecone multi-index
  - Añadir retry + exponential backoff ante errores del vector store remoto
  - Logging de latencia por shard para métricas RAGAS (Paso 11)
"""

from __future__ import annotations

import logging

from src.embeddings.generator import EmbeddingGenerator
from src.embeddings.vector_store import ShardedVectorStore
from src.etl.transformers.chunker import DocumentChunk

logger = logging.getLogger(__name__)


class VectorLoader:
    """Carga chunks (texto + embeddings) en el shard correcto del vector store.

    Paso 8 – Asignación a shards correctos + indexación distribuida.
    """

    def __init__(self):
        self._embedder = EmbeddingGenerator()
        self._store = ShardedVectorStore()

    def load(self, chunks: list[DocumentChunk]) -> int:
        """Genera embeddings y persiste los chunks en sus shards.

        Retorna el número de chunks cargados correctamente.
        """
        if not chunks:
            return 0

        # Agrupar por shard para batch upsert eficiente
        by_shard: dict[str, list[DocumentChunk]] = {}
        for chunk in chunks:
            by_shard.setdefault(chunk.shard, []).append(chunk)

        total_loaded = 0
        for shard, shard_chunks in by_shard.items():
            logger.info(f"Generando embeddings para {len(shard_chunks)} chunks → {shard}")
            texts = [c.text for c in shard_chunks]
            embeddings = self._embedder.encode(texts)

            loaded = self._store.upsert(
                shard=shard,
                ids=[c.chunk_id for c in shard_chunks],
                embeddings=embeddings,
                documents=texts,
                metadatas=[c.metadata for c in shard_chunks],
            )
            total_loaded += loaded
            logger.info(f"  {loaded} chunks cargados en {shard} "
                        f"(total en shard: {self._store.count(shard)})")

        return total_loaded

    def reset_shard(self, shard: str) -> None:
        self._store.delete_shard(shard)

    def store_stats(self) -> dict[str, int]:
        return self._store.stats()
