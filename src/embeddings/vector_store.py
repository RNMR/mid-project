"""
vector_store.py
===============
Paso 8  – Sharded Storage: ChromaDB como vector store distribuido (modo dev).
Paso 10 – Multi-región: interfaz diseñada para sustituir ChromaDB por
          Pinecone multi-index o Qdrant Distributed en producción.

Arquitectura de shards (colecciones ChromaDB):
  shard_legal          → documentos regulatorios (Ley N° 31557)
  shard_technical      → lineamientos técnicos internos
  shard_infrastructure → guías Docker, Kubernetes, AWS
  shard_operations     → encuestas CES y reportes operacionales

TODO (Paso 8 – producción):
  - Reemplazar PersistentClient con cliente Pinecone/Qdrant
  - Implementar replicación multi-región (Paso 10):
      shard_legal → región primaria us-east-1 + réplica eu-west-1
  - Añadir circuit breaker (Paso 10) ante fallos del vector store remoto
  - Semantic caching (Paso 10): Redis con TTL de 1h para queries frecuentes
"""

from __future__ import annotations

import logging
from pathlib import Path

from config.settings import CHROMA_DB_PATH

logger = logging.getLogger(__name__)


class ShardedVectorStore:
    """Gestiona colecciones ChromaDB como shards independientes por dominio.

    Paso 8 – Indexación distribuida (simulada localmente).
    Paso 3 – Shard Retrieval Pattern: cada shard se consulta de forma independiente.
    """

    def __init__(self, db_path: Path = CHROMA_DB_PATH):
        import chromadb
        db_path.mkdir(parents=True, exist_ok=True)
        self._client = chromadb.PersistentClient(path=str(db_path))
        self._collections: dict = {}
        logger.info(f"Vector store inicializado en: {db_path}")

    def _get_or_create(self, shard: str):
        if shard not in self._collections:
            self._collections[shard] = self._client.get_or_create_collection(
                name=shard,
                metadata={"hnsw:space": "cosine"},  # distancia coseno (embeddings L2-norm)
            )
        return self._collections[shard]

    def upsert(self, shard: str, ids: list[str], embeddings: list[list[float]],
               documents: list[str], metadatas: list[dict]) -> int:
        """Inserta o actualiza chunks en el shard indicado."""
        col = self._get_or_create(shard)
        # ChromaDB requiere metadatos sin valores None
        clean_metas = [_sanitize_meta(m) for m in metadatas]
        col.upsert(ids=ids, embeddings=embeddings, documents=documents, metadatas=clean_metas)
        logger.debug(f"Upsert {len(ids)} chunks → {shard}")
        return len(ids)

    def query(self, shard: str, query_embedding: list[float],
              n_results: int = 5, where: dict | None = None) -> dict:
        """Consulta un shard específico por similitud semántica.

        Paso 3  – Sharded Retrieval Pattern.
        Paso 9  – Multi-index retrieval: llamar a múltiples shards y fusionar.
        Paso 11 – Observabilidad: el caller debe registrar latencia de esta llamada.
        """
        col = self._get_or_create(shard)
        kwargs: dict = {"query_embeddings": [query_embedding], "n_results": n_results,
                        "include": ["documents", "metadatas", "distances"]}
        if where:
            kwargs["where"] = where
        return col.query(**kwargs)

    def count(self, shard: str) -> int:
        return self._get_or_create(shard).count()

    def delete_shard(self, shard: str) -> None:
        """Elimina todos los chunks de un shard (útil para re-ingesta)."""
        try:
            self._client.delete_collection(shard)
            self._collections.pop(shard, None)
            logger.info(f"Shard eliminado: {shard}")
        except Exception:
            pass

    def get_by_source(self, shard: str, source_file: str) -> list[dict]:
        """Retorna todos los chunks de un documento específico por source_file exacto.

        Útil como fallback de routing léxico cuando embedding similarity es baja.
        """
        col = self._get_or_create(shard)
        results = col.get(
            where={"source_file": {"$eq": source_file}},
            include=["documents", "metadatas"],
        )
        ids = results.get("ids", [])
        docs = results.get("documents", [])
        metas = results.get("metadatas", [])
        return [{"id": i, "document": d, "metadata": m}
                for i, d, m in zip(ids, docs, metas)]

    def stats(self) -> dict[str, int]:
        """Retorna conteo de chunks por shard para observabilidad (Paso 11)."""
        shards = ["shard_legal", "shard_technical", "shard_infrastructure", "shard_operations"]
        return {s: self.count(s) for s in shards}


def _sanitize_meta(meta: dict) -> dict:
    """ChromaDB solo acepta str/int/float/bool como valores de metadatos."""
    clean = {}
    for k, v in meta.items():
        if isinstance(v, (str, int, float, bool)):
            clean[str(k)] = v
        elif v is None:
            clean[str(k)] = ""
        else:
            clean[str(k)] = str(v)
    return clean
