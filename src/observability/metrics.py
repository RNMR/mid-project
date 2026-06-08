"""
metrics.py
==========
Paso 11 – Observabilidad: métricas Prometheus del sistema RAG distribuido.

Métricas expuestas en GET /metrics:
  rag_query_latency_seconds   – latencia total por query (buckets para SLA)
  rag_shard_latency_seconds   – latencia de retrieval por shard individual
  rag_shard_queries_total     – queries por shard (tasa de uso)
  rag_shard_errors_total      – errores por shard (circuit breaker input)
  rag_chunks_retrieved_total  – chunks recuperados por shard
  rag_rerank_score            – distribución de scores top-1 del reranker
  rag_indexed_chunks          – chunks indexados en ChromaDB por shard (gauge)

Evaluación RAGAS (diseño – Paso 11):
  Faithfulness     : fracción de la respuesta soportada por el contexto recuperado
  Answer Relevancy : similitud semántica pregunta ↔ respuesta
  Context Precision: % de chunks relevantes entre los top-k devueltos
  → Medirlos offline con ragas.evaluate() sobre un golden dataset de 20-50 queries.

Logs estructurados:
  Cada query registra: query_id, shards, latency_ms, chunks, top_score
  Compatible con CloudWatch Logs Insights / Loki / Elasticsearch.
"""

from __future__ import annotations

import logging
import time
import uuid
from contextlib import contextmanager

from prometheus_client import Counter, Gauge, Histogram

logger = logging.getLogger(__name__)

# ── Métricas Prometheus ────────────────────────────────────────────────────────

# Latencia total de cada request al endpoint /query
QUERY_LATENCY = Histogram(
    "rag_query_latency_seconds",
    "Latencia total de una query RAG end-to-end",
    ["status"],                               # status: ok | error
    buckets=[0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0],
)

# Latencia de retrieval por shard individual (embedding + ChromaDB query)
SHARD_LATENCY = Histogram(
    "rag_shard_latency_seconds",
    "Latencia de retrieval por shard",
    ["shard"],
    buckets=[0.05, 0.1, 0.25, 0.5, 1.0, 2.0],
)

# Contadores de operaciones
SHARD_QUERIES = Counter(
    "rag_shard_queries_total",
    "Total de queries enviadas a cada shard",
    ["shard"],
)

SHARD_ERRORS = Counter(
    "rag_shard_errors_total",
    "Errores de retrieval por shard",
    ["shard", "error_type"],
)

CHUNKS_RETRIEVED = Counter(
    "rag_chunks_retrieved_total",
    "Chunks recuperados por shard",
    ["shard"],
)

# Distribución del score top-1 después del reranker
RERANK_SCORE = Histogram(
    "rag_rerank_score",
    "Score del chunk #1 después de RRF/reranking (distancia coseno)",
    buckets=[0.0, 0.05, 0.1, 0.15, 0.2, 0.3, 0.5, 1.0],
)

# Gauge: estado del índice (se actualiza tras cada ETL)
INDEXED_CHUNKS = Gauge(
    "rag_indexed_chunks",
    "Chunks actualmente indexados en ChromaDB",
    ["shard"],
)


# ── Helpers públicos ───────────────────────────────────────────────────────────

@contextmanager
def measure_query_latency(status: str = "ok"):
    """Mide la latencia total de un request /query."""
    t0 = time.perf_counter()
    try:
        yield
    except Exception:
        status = "error"
        raise
    finally:
        QUERY_LATENCY.labels(status=status).observe(time.perf_counter() - t0)


@contextmanager
def measure_shard_latency(shard: str):
    """Mide la latencia de retrieval en un shard específico."""
    t0 = time.perf_counter()
    try:
        yield
    finally:
        SHARD_LATENCY.labels(shard=shard).observe(time.perf_counter() - t0)


def record_shard_query(shard: str, chunks_returned: int) -> None:
    SHARD_QUERIES.labels(shard=shard).inc()
    CHUNKS_RETRIEVED.labels(shard=shard).inc(chunks_returned)


def record_shard_error(shard: str, error_type: str = "retrieval_error") -> None:
    SHARD_ERRORS.labels(shard=shard, error_type=error_type).inc()


def record_rerank_score(top_score: float) -> None:
    RERANK_SCORE.observe(top_score)


def update_indexed_chunks(shard: str, count: int) -> None:
    INDEXED_CHUNKS.labels(shard=shard).set(count)


def log_retrieval_event(query: str, shards: list[str], chunks_count: int,
                        latency_ms: float, top_score: float) -> None:
    """Log estructurado de un evento de retrieval (CloudWatch / Loki compatible)."""
    logger.info(
        "retrieval_event query_id=%s shards=%s chunks=%d latency_ms=%.1f top_score=%.4f query=%r",
        uuid.uuid4().hex[:8], shards, chunks_count, latency_ms, top_score, query[:80],
    )
