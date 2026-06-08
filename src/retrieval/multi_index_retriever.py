"""
multi_index_retriever.py
========================
Paso 3  – Multi-Index Retrieval Pattern: consulta múltiples shards en paralelo.
Paso 9  – Re-ranking: fusiona y re-ordena resultados cross-shard.

Flujo completo de una query RAG:
  1. QueryRewriter   → genera variantes de la query
  2. ShardSelector   → decide qué shards consultar
  3. MultiIndexRetriever → consulta shards en paralelo (ThreadPoolExecutor)
  4. Reranker        → re-ordena resultados fusionados (cross-encoder / RRF)
  5. Claude API      → genera respuesta usando los chunks re-ordenados

TODO – Implementar:
  1. Paralelizar queries a shards con concurrent.futures.ThreadPoolExecutor
  2. Integrar EmbeddingGenerator para vectorizar la query antes de buscar
  3. Conectar con ShardedVectorStore.query() por cada shard seleccionado
  4. Aplicar Reranker sobre resultados fusionados
  5. Pasar top-k chunks a Claude para generar respuesta final
  6. Registrar métricas de latencia por shard (Paso 11)
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

from src.embeddings.generator import EmbeddingGenerator
from src.embeddings.vector_store import ShardedVectorStore
from src.retrieval.reranker import RetrievedChunk, Reranker, reciprocal_rank_fusion
from src.retrieval.shard_selector import ShardSelector
from src.retrieval.query_rewriter import QueryRewriter
from src.observability.metrics import (
    measure_shard_latency, record_shard_query,
    record_shard_error, record_rerank_score,
)
from config.settings import TOP_K_PER_SHARD, RERANK_TOP_K

logger = logging.getLogger(__name__)


class MultiIndexRetriever:
    """Retrieval distribuido: consulta paralela de múltiples shards + reranking.

    Paso 3 – Multi-Index Retrieval Pattern + Sharded Retrieval Pattern.
    """

    def __init__(self):
        self._embedder   = EmbeddingGenerator()
        self._store      = ShardedVectorStore()
        self._selector   = ShardSelector()
        self._rewriter   = QueryRewriter()
        self._reranker   = Reranker()

    # Document-level routing: (query_keyword, product_keyword) → source_file exacto
    # Cuando bge-small-en-v1.5 no puede rankear bien por ser modelo inglés,
    # inyectamos directamente los chunks del documento correcto por metadata.
    _DOCUMENT_ROUTES: list[tuple[tuple[str, ...], str, str]] = [
        # (keywords_en_query, shard, source_file_exacto)
        (("nombr", "dynamodb"),      "shard_technical",
         "Lineamiento de Nombramiento de Objetos en DynamoDB-080825-160720.pdf"),
        (("nomenclatura", "dynamodb"), "shard_technical",
         "Lineamiento de Nombramiento de Objetos en DynamoDB-080825-160720.pdf"),
        (("lineamiento", "dynamodb", "tabla"), "shard_technical",
         "Lineamiento de Nombramiento de Objetos en DynamoDB-080825-160720.pdf"),
    ]

    # Palabras clave de producto → fragmento de nombre de archivo (para score boost)
    _SOURCE_BOOST: dict[str, str] = {
        "dynamodb": "dynamodb",
        "dynamo":   "dynamodb",
        "docker":   "docker",
        "kubernetes": "kubernetes",
        "k8s":      "kubernetes",
        "terraform": "terraform",
    }

    def retrieve(self, query: str, top_k: int = RERANK_TOP_K) -> list[RetrievedChunk]:
        """Pipeline completo de retrieval para una query de usuario."""
        sep = "─" * 60
        logger.info(f"\n{sep}\nQUERY: {query}\n{sep}")

        # Paso 9 – Query rewriting
        queries = self._rewriter.rewrite(query)
        logger.info(f"[REWRITE] {len(queries)} variante(s):")
        for i, q in enumerate(queries):
            logger.info(f"  [{i}] {q}")

        # Paso 3 – Selección de shards
        shards = self._selector.select(query)
        logger.info(f"[SHARDS]  seleccionados: {shards}")

        query_lower = query.lower()

        # Document routing léxico
        routed_chunks = self._apply_document_routing(query_lower)

        # Source boost por producto
        source_boost_key = next(
            (v for k, v in self._SOURCE_BOOST.items() if k in query_lower), None
        )
        if source_boost_key:
            logger.info(f"[BOOST]   source_boost_key='{source_boost_key}'")

        # Vectorizar TODAS las variantes de query
        query_vecs = self._embedder.encode(queries)

        # Consultar shards en paralelo
        all_results: list[list[RetrievedChunk]] = []

        if routed_chunks:
            all_results.append(routed_chunks)
            logger.info(f"[ROUTING] {len(routed_chunks)} chunks inyectados del doc exacto")

        tasks = [(shard, vec) for shard in shards for vec in query_vecs]
        with ThreadPoolExecutor(max_workers=max(len(shards), 4)) as pool:
            futures = {
                pool.submit(self._query_shard, shard, vec, TOP_K_PER_SHARD,
                            source_boost_key): (shard, i)
                for i, (shard, vec) in enumerate(tasks)
            }
            for fut in as_completed(futures):
                shard, i = futures[fut]
                try:
                    chunks = fut.result()
                    if chunks:
                        all_results.append(chunks)
                        record_shard_query(shard, len(chunks))   # Paso 11
                        logger.info(f"[VECTOR]  {shard} variante[{i % len(query_vecs)}]: "
                                    f"{len(chunks)} chunks")
                        for c in chunks:
                            src = (c.metadata or {}).get("source_file", c.chunk_id)[:50]
                            logger.info(f"           dist={c.score:.4f}  {src}")
                except Exception as exc:
                    record_shard_error(shard)                    # Paso 11
                    logger.error(f"[ERROR]   {shard}: {exc}")

        if not all_results:
            return []

        # Paso 9 – Fusión RRF
        merged = reciprocal_rank_fusion(all_results)
        logger.info(f"\n[RRF]     {len(merged)} chunks únicos tras fusión:")
        for c in merged[:10]:
            src = (c.metadata or {}).get("source_file", c.chunk_id)[:55]
            sec = (c.metadata or {}).get("section_title", "")
            logger.info(f"  score={c.score:.4f}  [{sec}]  {src}")

        # Re-ranking
        reranked = self._reranker.rerank(query, merged, top_k=top_k)
        logger.info(f"\n[FINAL]   top-{len(reranked)} chunks enviados al LLM:")
        for rank, c in enumerate(reranked, 1):
            src = (c.metadata or {}).get("source_file", c.chunk_id)[:55]
            sec = (c.metadata or {}).get("section_title", "")
            logger.info(f"  #{rank}  score={c.score:.4f}  [{sec}]  {src}")
            logger.info(f"       {c.text[:120].replace(chr(10), ' ')!r}")
        logger.info(sep)

        if reranked:
            record_rerank_score(reranked[0].score)               # Paso 11

        return reranked

    def _apply_document_routing(self, query_lower: str) -> list[RetrievedChunk]:
        """Routing léxico: inyecta chunks de un documento específico cuando todos
        los keywords de una ruta aparecen en la query.

        Soluciona el problema de embedding quality para textos técnicos en español
        con modelos ingleses (bge-small-en-v1.5).
        """
        for keywords, shard, source_file in self._DOCUMENT_ROUTES:
            if all(kw in query_lower for kw in keywords):
                try:
                    items = self._store.get_by_source(shard, source_file)
                    chunks = [
                        RetrievedChunk(
                            chunk_id=item["id"],
                            text=item["document"],
                            metadata=item["metadata"],
                            score=0.05,  # distancia coseno muy baja = alta prioridad en RRF
                            shard=shard,
                        )
                        for item in items
                    ]
                    logger.info(f"Routing léxico → {source_file} ({len(chunks)} chunks)")
                    return chunks
                except Exception as exc:
                    logger.warning(f"Document routing falló ({exc})")
        return []

    def _query_shard(self, shard: str, query_vec: list[float],
                     n_results: int, source_boost_key: str | None = None) -> list[RetrievedChunk]:
        results = self._store.query(shard, query_vec, n_results=n_results)
        chunks: list[RetrievedChunk] = []
        if not results or not results.get("documents"):
            return chunks
        docs      = results["documents"][0]
        metas     = results["metadatas"][0]
        distances = results["distances"][0]
        ids_list  = results.get("ids", [[]])[0]
        for doc, meta, dist, cid in zip(docs, metas, distances, ids_list):
            score = dist
            # Boost: si la query menciona un producto específico (ej. "dynamodb"),
            # bajar la distancia coseno de chunks cuyo source_file lo contiene.
            # Distancia coseno: menor = más relevante, por eso se multiplica por < 1.
            if source_boost_key:
                source = (meta.get("source_file") or cid).lower()
                if source_boost_key in source:
                    score *= 0.5  # boost: duplica la relevancia efectiva
                    logger.debug(f"Source boost aplicado a {cid} (source_key={source_boost_key})")
            chunks.append(RetrievedChunk(
                chunk_id=cid, text=doc, metadata=meta,
                score=score, shard=shard,
            ))
        return chunks
