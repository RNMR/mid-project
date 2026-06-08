"""
config/settings.py
==================
Paso 1  – Definición del caso de uso: dominios, SLAs y reglas de negocio.
Paso 2  – Selección de modelo e infraestructura: embedding model, vector backend.
Paso 10 – Optimización multi-región: región primaria y réplicas configurables.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# ── Rutas ─────────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent

# Directorios fuente por dominio (Paso 1 – dominios documentales)
DOMAIN_PATHS: dict[str, Path] = {
    "legal":          BASE_DIR / "data" / "sources" / "LEGAL",
    "technical":      BASE_DIR / "data" / "sources" / "MANUALES",
    "infrastructure": BASE_DIR / "data" / "sources" / "DOC WEB",
    "operations":     BASE_DIR / "data" / "sources" / "ENCUESTAS",
}

# Directorio de persistencia del vector store local
CHROMA_DB_PATH = BASE_DIR / "data" / "chroma_db"

# ── Paso 2: Modelo de embeddings ──────────────────────────────────────────────
# Open-source: BAAI/bge-small-en-v1.5
#   Justificación:
#     - Costo cero de inferencia (local)
#     - 384 dimensiones → índices compactos, baja latencia
#     - Buen recall en textos técnicos español/inglés
#     - Migración transparente a BGE-large o E5 en producción
EMBEDDING_MODEL   = "BAAI/bge-small-en-v1.5"
EMBEDDING_DIM     = 384
EMBEDDING_BATCH   = 32           # chunks por lote de inferencia

# Cross-encoder para re-ranking (Paso 9)
RERANKER_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"

# ── Paso 7: Chunking ──────────────────────────────────────────────────────────
CHUNK_SIZE_TOKENS    = 512
CHUNK_OVERLAP_TOKENS = 50
MIN_CHUNK_TOKENS     = 40
CSV_ROWS_PER_CHUNK   = 20   # filas de encuesta por chunk operacional

# ── Paso 9: Retrieval ─────────────────────────────────────────────────────────
TOP_K_PER_SHARD = 8
RERANK_TOP_K    = 5

# ── LLM (Paso 9: query rewriting + respuesta) ────────────────────────────────
# Ollama corre local: brew install ollama && ollama pull llama3.2
OLLAMA_MODEL    = os.getenv("OLLAMA_MODEL", "llama3.2")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

# ── Paso 10: Multi-región ─────────────────────────────────────────────────────
PRIMARY_REGION  = os.getenv("AWS_REGION", "us-east-1")
REPLICA_REGIONS = os.getenv("REPLICA_REGIONS", "us-west-2").split(",")

# ── Paso 11: Observabilidad ───────────────────────────────────────────────────
LOG_LEVEL    = os.getenv("LOG_LEVEL", "INFO")
METRICS_PORT = int(os.getenv("METRICS_PORT", "9090"))
