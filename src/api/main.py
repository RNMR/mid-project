"""
api/main.py
===========
Paso 5  – Orquestación: API REST del sistema RAG distribuido.
Paso 4  – Contenerización: este módulo es la entrada del Dockerfile.api.

Endpoints:
  POST /query   – consulta RAG multi-shard con reranking
  GET  /health  – health check para Kubernetes readiness probe (Paso 5)
  GET  /metrics – métricas Prometheus (Paso 11)
  GET  /shards  – estadísticas por shard (Paso 11)

TODO – Implementar:
  1. Endpoint /query: integrar MultiIndexRetriever + Claude respuesta final
  2. Autenticación: JWT o API key (secret externo, Paso 4)
  3. Rate limiting por dominio / usuario (Paso 10 – SLAs)
  4. Circuit breaker: si un shard no responde → fallback a shards disponibles (Paso 10)
  5. Semantic caching con Redis: cachear respuestas por embedding de query (Paso 10)
  6. Trazas distribuidas: OpenTelemetry → Jaeger / AWS X-Ray (Paso 11)

Orquestación (Paso 5):
  - Serverless: desplegar como AWS Lambda (handler en lambda_handler.py)
    o Google Cloud Run (este mismo main.py funciona con gunicorn)
  - Kubernetes: deployment + HPA + ingress (ver docker/docker-compose.yml)
"""

from __future__ import annotations

import logging
import time

from fastapi import FastAPI, HTTPException
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST

from config.settings import OLLAMA_MODEL
from src.retrieval.multi_index_retriever import MultiIndexRetriever
from src.observability.metrics import (
    measure_query_latency, log_retrieval_event, update_indexed_chunks,
)

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Distributed RAG API",
    description="Paso 5 – API de retrieval distribuido con sharding por dominio",
    version="0.1.0-stub",
)

_retriever: MultiIndexRetriever | None = None


def _get_retriever() -> MultiIndexRetriever:
    global _retriever
    if _retriever is None:
        _retriever = MultiIndexRetriever()
    return _retriever


# ── Schemas ───────────────────────────────────────────────────────────────────

class QueryRequest(BaseModel):
    query: str
    top_k: int = 3
    domain_filter: str | None = None   # opcional: forzar shard específico


class QueryResponse(BaseModel):
    answer: str
    sources: list[dict]
    shards_queried: list[str]
    latency_ms: float


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    """Kubernetes readiness/liveness probe (Paso 5)."""
    return {"status": "ok", "version": "0.1.0-stub"}


@app.get("/metrics", response_class=PlainTextResponse)
def metrics():
    """Endpoint de métricas Prometheus – scrapeable por Prometheus/Grafana (Paso 11)."""
    return PlainTextResponse(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.get("/shards")
def shard_stats():
    """Estadísticas de chunks por shard – observabilidad (Paso 11)."""
    from src.embeddings.vector_store import ShardedVectorStore
    store = ShardedVectorStore()
    stats = store.stats()
    # Actualizar gauge de chunks indexados (Paso 11)
    for shard, count in stats.items():
        update_indexed_chunks(shard, count)
    return {"shards": stats}


@app.post("/query", response_model=QueryResponse)
def query_rag(req: QueryRequest):
    """Endpoint principal de retrieval RAG multi-shard con métricas Prometheus (Paso 11)."""
    t0 = time.time()
    retriever = _get_retriever()

    with measure_query_latency():                                # Paso 11
        chunks = retriever.retrieve(req.query, top_k=req.top_k)

        if not chunks:
            raise HTTPException(status_code=404, detail="No se encontraron documentos relevantes")

        answer = _generate_answer(req.query, chunks)

    latency_ms = round((time.time() - t0) * 1000, 2)
    shards = list({c.shard for c in chunks})
    top_score = chunks[0].score if chunks else 0.0

    log_retrieval_event(req.query, shards, len(chunks), latency_ms, top_score)  # Paso 11

    return QueryResponse(
        answer=answer,
        sources=[{"chunk_id": c.chunk_id, "shard": c.shard,
                  "score": c.score, "preview": c.text[:200]} for c in chunks],
        shards_queried=shards,
        latency_ms=latency_ms,
    )


_RAG_SYSTEM_PROMPT = """Eres un asistente experto en documentación técnica, legal y operacional.
Responde la pregunta del usuario usando EXCLUSIVAMENTE la información del contexto proporcionado.
Si el contexto no contiene información suficiente para responder, dilo claramente.
Responde en el mismo idioma de la pregunta. Sé preciso y conciso."""


def _generate_answer(query: str, chunks: list) -> str:
    """Genera respuesta RAG usando Ollama (Paso 9 – respuesta generativa)."""
    context = "\n\n---\n\n".join(
        f"[Fuente: {c.shard} | doc: {c.chunk_id.rsplit('_', 1)[0]}]\n{c.text[:1500]}" for c in chunks
    )
    try:
        import ollama
        response = ollama.chat(
            model=OLLAMA_MODEL,
            messages=[
                {"role": "system", "content": _RAG_SYSTEM_PROMPT},
                {"role": "user", "content": f"Contexto:\n{context}\n\nPregunta: {query}"},
            ],
            options={"temperature": 0.1},
        )
        return response["message"]["content"].strip()
    except ImportError:
        return "Ollama no instalado. Ejecutar: pip install ollama && ollama pull llama3.2"
    except Exception as exc:
        logger.error(f"Error generando respuesta: {exc}")
        return f"Error generando respuesta: {exc}"


# ── Entrypoint local ──────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(name)s  %(message)s",
        datefmt="%H:%M:%S",
    )
    # Silenciar loggers ruidosos de librerías externas
    logging.getLogger("chromadb").setLevel(logging.WARNING)
    logging.getLogger("sentence_transformers").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    uvicorn.run("src.api.main:app", host="0.0.0.0", port=8000, reload=True)
