# Distributed RAG Architecture – Proyecto 9
## Diseño de Infraestructura Escalable – BSG Institute

Sistema RAG distribuido con sharding por dominio, multi-index retrieval,
query rewriting y re-ranking avanzado.

---

## Mapa del proyecto vs Assignment (12 pasos)

| Paso | Componente | Estado | Archivo(s) clave |
|------|-----------|--------|-----------------|
| 1 | Caso de uso + KPIs | ✅ Documentado | `config/domains.yaml`, `docs/architecture.md` |
| 2 | Modelo + Infraestructura | ✅ Configurado | `config/settings.py`, `src/embeddings/generator.py` |
| 3 | Patrón de diseño LLM | ✅ Implementado | `src/retrieval/shard_selector.py`, `docs/architecture.md` |
| 4 | Docker / Contenerización | ✅ Implementado | `docker/Dockerfile.etl`, `docker/Dockerfile.api`, `docker/docker-compose.yml` |
| 5 | Orquestación | ✅ Stub documentado | `docker/docker-compose.yml`, `src/api/main.py` |
| 6 | Arquitectura Distribuida | ✅ Diagrama Mermaid | `docs/architecture.md` |
| 7 | **ETL + Sharding** | ✅ **IMPLEMENTADO** | `src/etl/` completo |
| 8 | **Embeddings + Vector Storage** | ✅ **IMPLEMENTADO** | `src/embeddings/` completo |
| 9 | Reranking + Query Rewriting | ✅ Implementado | `src/retrieval/reranker.py`, `src/retrieval/query_rewriter.py`, `src/api/main.py` |
| 10 | Multi-Región + HA | 🔨 Stub documentado | `src/embeddings/vector_store.py`, `docs/architecture.md` |
| 11 | Observabilidad | 🔨 Stub documentado | `src/observability/metrics.py` |
| 12 | Documentación | ✅ Implementado | `docs/user_guide.md`, `docs/admin_guide.md` |

**Leyenda**: ✅ Implementado/funcional · 🔨 Stub con TODOs detallados

---

## Inicio rápido

```bash
# 1. Instalar dependencias
pip install -r requirements.txt

# 2. Instalar Ollama (LLM local, gratis – solo una vez)
brew install ollama
ollama pull llama3.2        # ~2GB descarga única

# 3. Indexar documentos (Pasos 7+8)
python run_etl.py

# 4. Iniciar Ollama en terminal separada
ollama serve

# 5. Iniciar API (Paso 5)
python -m src.api.main
# → http://localhost:8000/docs
```

---

## Estructura del proyecto

```
mid project/
├── config/
│   ├── settings.py         # Pasos 1,2,10 – config central
│   └── domains.yaml        # Paso 1 – dominios, SLAs, KPIs
├── src/
│   ├── etl/                # ✅ Pasos 7+8 – IMPLEMENTADO
│   │   ├── extractors/     #   PDF + CSV (Qualtrics)
│   │   ├── transformers/   #   Cleaner + SmartChunker + MetadataEnricher
│   │   └── loaders/        #   ShardRouter + VectorLoader
│   ├── embeddings/         # ✅ Paso 8 – IMPLEMENTADO
│   │   ├── generator.py    #   BGE bge-small-en-v1.5
│   │   └── vector_store.py #   ChromaDB shards
│   ├── retrieval/          # ✅ Pasos 3,9 – Implementado
│   │   ├── shard_selector.py
│   │   ├── multi_index_retriever.py
│   │   ├── query_rewriter.py
│   │   └── reranker.py     #   RRF implementado
│   ├── api/                # ✅ Paso 5 – FastAPI con respuesta generativa Ollama
│   │   └── main.py
│   └── observability/      # 🔨 Paso 11 – Stub documentado
│       └── metrics.py
├── docker/                 # ✅ Paso 4 – Dockerfiles multi-stage
│   ├── Dockerfile.etl
│   ├── Dockerfile.api
│   └── docker-compose.yml
├── docs/                   # ✅ Paso 12 – Documentación
│   ├── architecture.md     #   Diagramas Mermaid (Pasos 3,6,7,8,10)
│   ├── user_guide.md
│   └── admin_guide.md
├── data/                   
│   ├── chroma_db/              # vector store local (generado por ETL)
│   └── sources/                # pdfs y excel
│   │   ├── LEGAL/              # shard_legal
│   │   ├── MANUALES/           # shard_technical
│   │   ├── DOC WEB/            # shard_infrastructure
│   │   └── ENCUESTAS/          # shard_operations
├── run_etl.py              # ✅ Entrypoint ETL
└── requirements.txt
```

---

## Tecnologías seleccionadas (Paso 2)

| Componente | Tecnología | Justificación |
|-----------|-----------|---------------|
| Embeddings | `BAAI/bge-small-en-v1.5` | Open-source, 384d, costo $0, bilingüe ES/EN |
| Vector store (dev) | ChromaDB | Persistencia local, shards = collections |
| Vector store (prod) | Pinecone multi-index | SLA 99.9%, multi-región nativo, cosine search |
| LLM | Ollama + llama3.2 | Local, sin costo, sin API key – query rewriting + respuesta final |
| Re-ranking | cross-encoder/ms-marco-MiniLM-L-6-v2 | Local, eficiente en CPU |
| API | FastAPI + uvicorn | Async, OpenAPI docs automáticas |
| Contenedores | Docker multi-stage, non-root | Seguridad + slim images |
| Observabilidad | Prometheus + structlog | Métricas por shard + logs estructurados |
