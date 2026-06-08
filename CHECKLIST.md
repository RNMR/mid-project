# Checklist – Proyecto 9: Distributed RAG Architecture
## Estado por paso del assignment

---

## ✅ Paso 1 – Definición Avanzada del Caso de Uso (10 pts)

**Completado:**
- Dominios documentales definidos: Legal, Technical, Infrastructure, Operations
- SLAs por dominio (0.5s – 2.0s)
- Volumen por dominio documentado
- Reglas de negocio por dominio
- KPIs definidos (retrieval accuracy, latencia p99, reranking quality)

**Archivo:** `config/domains.yaml`

**Te falta:**
- [ ] Redactar 1–2 párrafos narrativos del caso de uso empresarial (quién usa el sistema, para qué, qué problema resuelve). El YAML tiene los datos técnicos pero el profesor pedirá una descripción del escenario.

---

## ✅ Paso 2 – Selección del Modelo + Infraestructura (10 pts)

**Completado:**
- Embedding model seleccionado: `BAAI/bge-small-en-v1.5` (open-source, BGE)
- Vector store dev: ChromaDB con colecciones como shards
- Vector store prod: Pinecone multi-index (documentado)
- Justificación de latencia, costo y capacidad de sharding en `config/settings.py` y `README.md`

**Te falta:**
- [ ] Tabla de comparación de costos mensuales aproximados (Pinecone vs Qdrant vs AlloyDB+pgvector). El assignment pide "Costo mensual aproximado" explícito.
- [ ] Justificación escrita de por qué NO se eligió AWS Titan o Azure OpenAI (o dejar claro que es migración opcional).

---

## ✅ Paso 3 – Patrón de Diseño LLM (10 pts)

**Completado:**
- Sharded Retrieval Pattern implementado (`src/retrieval/shard_selector.py`)
- Multi-Index Retrieval Pattern (`src/retrieval/multi_index_retriever.py`)
- Domain Router Pattern (`src/etl/loaders/shard_router.py`)
- Query Rewriting Pattern (stub conectado)
- Reranking Pattern (stub con RRF implementado)
- Diagrama Mermaid completo en `docs/architecture.md`

**Te falta:**
- [ ] Revisar el diagrama Mermaid en `docs/architecture.md` y renderizarlo (GitHub lo hace automáticamente, o usar mermaid.live). El profesor pedirá el diagrama visible.
- [ ] Describir los trade-offs técnicos de cada patrón elegido (1 párrafo por patrón).

---

## ✅ Paso 4 – Contenerización con Docker (8 pts)

**Completado:**
- `docker/Dockerfile.etl` – multi-stage, non-root, slim base
- `docker/Dockerfile.api` – multi-stage, non-root
- `docker/docker-compose.yml` – orquestación local completa
- Secrets externos vía `.env` (nunca hardcodeados)

**Te falta:**
- [ ] Ejecutar `docker compose build` para verificar que los Dockerfiles compilan sin error en tu máquina.
- [ ] Captura de pantalla o log del build exitoso para el entregable.

---

## ✅ Paso 5 – Orquestación (8 pts)

**Completado:**
- `src/api/main.py` – FastAPI con endpoints REST completos
- `docker/docker-compose.yml` – orquestación local con healthchecks y Prometheus
- **Decisión de prod: AWS EKS (Kubernetes)**
  - Justificación: cold start de Lambda (~10s) viola el SLA de 2s por el modelo de embeddings en RAM
  - Cloud Run descartado: menos control sobre anti-affinity multi-AZ y HPA por métricas custom
- `k8s/namespace-and-pvc.yaml` – Namespace `rag` + PVCs en AWS EFS (ReadWriteMany)
- `k8s/configmap.yaml` – ConfigMap con variables no-secretas
- `k8s/deployment-api.yaml` – Deployment: 2 réplicas, anti-affinity por AZ, liveness + readiness probes, non-root
- `k8s/hpa.yaml` – HPA: 2–8 réplicas, escala por CPU>60% o memoria>75%
- `k8s/service.yaml` – ClusterIP + Ingress nginx
- `k8s/cronjob-etl.yaml` – CronJob: re-indexación dominical 02:00 AM (Perú)

---

## ✅ Paso 6 – Arquitectura Completa Distribuida (10 pts)

**Completado:**
- Diagrama Mermaid de arquitectura distribuida en `docs/architecture.md`
- Shards por dominio, multi-index, replicación, reranking, query rewriting, routing y observabilidad incluidos en el diagrama

**Te falta:**
- [ ] Verificar que el diagrama Mermaid renderiza correctamente (pegar en mermaid.live).
- [ ] Agregar descripción de la replicación multi-región (activa/pasiva o activa/activa) con las regiones específicas elegidas.

---

## ✅ Paso 7 – Pipeline de Ingesta + Sharding (10 pts) — NÚCLEO IMPLEMENTADO

**Completado:**
- Extracción PDF (`src/etl/extractors/pdf_extractor.py`) – pdfplumber, limpieza de ruido
- Extracción CSV Qualtrics (`src/etl/extractors/csv_extractor.py`) – 3 filas de header, anonimización PII
- Limpieza y normalización (`src/etl/transformers/cleaner.py`)
- Chunking semántico/sección + token-based dinámico (`src/etl/transformers/chunker.py`)
- Enriquecimiento de metadatos (`src/etl/transformers/metadata_enricher.py`)
- Shard routing por dominio (`src/etl/loaders/shard_router.py`)
- Pipeline completo orquestado (`src/etl/pipeline.py`)
- **Validado en dry-run: 15 docs → 5,568 chunks sin errores**

**Te falta:**
- [ ] Nada técnico. Para el entregable: documentar en el informe los resultados del dry-run (tabla de chunks por dominio está en este archivo).

---

## ✅ Paso 8 – Generación de Embeddings + Sharded Storage (6 pts)

**Completado:**
- `src/embeddings/generator.py` – BGE bge-small-en-v1.5, batch inference, normalización L2
- `src/embeddings/vector_store.py` – ChromaDB con colecciones por shard, upsert en batch
- ✅ ETL ejecutado: ChromaDB poblado con embeddings reales

**Te falta:**
- [ ] Capturar métricas de latencia y throughput del embedding desde los logs para incluir en el informe.

---

## ✅ Paso 9 – Re-ranking + Query Rewriting (6 pts)

**Completado:**
- `src/retrieval/reranker.py` – RRF (Reciprocal Rank Fusion) implementado
- `src/retrieval/query_rewriter.py` – ✅ implementado con Ollama (llama3.2, local, gratis)
- `src/retrieval/multi_index_retriever.py` – retrieval paralelo sobre múltiples shards con RRF
- `src/api/main.py` – ✅ respuesta generativa implementada con Ollama
- Bug corregido: shard selector ya no incluye shards con score=0

**Te falta:**
- [ ] Ejecutar al menos 3 queries de prueba y documentar comparativa antes/después de reranking para el informe
- [ ] Implementar el cross-encoder en `reranker.py` para reranking más preciso (opcional, RRF ya funciona)

---

## 🔨 Paso 10 – Optimización Multi-Región y Alta Disponibilidad (7 pts)

**Completado (diseño documentado):**
- Variables de entorno para multi-región en `config/settings.py`
- Arquitectura activa/pasiva documentada en `docs/architecture.md`

**Te falta (es mayormente documentación/diseño):**
- [ ] Calcular latencia estimada por región (usar tablas de AWS/GCP de latencia inter-región).
- [ ] Calcular costo de tráfico cross-region para el volumen estimado de queries.
- [ ] Calcular ahorro estimado con semantic caching (ej. 30% cache hit rate → X% reducción de costo).
- [ ] Describir la estrategia de circuit breaker y fallback automático (puede ser solo diseño).

---

## ✅ Paso 11 – Observabilidad y Métricas (7 pts)

**Completado:**
- `src/observability/metrics.py` – métricas Prometheus implementadas y conectadas:
  - `rag_query_latency_seconds` – Histogram con buckets para SLA (0.1s → 10s)
  - `rag_shard_latency_seconds` – Histogram por shard individual
  - `rag_shard_queries_total` – Counter de queries por shard
  - `rag_shard_errors_total` – Counter de errores por shard (input para circuit breaker)
  - `rag_chunks_retrieved_total` – Counter de chunks recuperados
  - `rag_rerank_score` – Histogram de scores top-1 post-reranking
  - `rag_indexed_chunks` – Gauge de chunks en ChromaDB por shard
- `src/api/main.py` – `/metrics` endpoint expuesto (formato Prometheus)
- `src/api/main.py` – `measure_query_latency()` wrapping el endpoint `/query`
- `src/retrieval/multi_index_retriever.py` – `.inc()` en shard queries, errores y rerank score
- Log estructurado por query: `query_id`, `shards`, `chunks`, `latency_ms`, `top_score`
- Evaluación RAGAS documentada en `metrics.py`: Faithfulness, Answer Relevancy, Context Precision

**Te falta:**
- [ ] Abrir `http://localhost:8000/metrics` tras reiniciar y verificar que aparecen las métricas
- [ ] Dashboard de Grafana (opcional): JSON en `docker/grafana/` con los 3 paneles principales

---

## ✅ Paso 12 – Documentación Final Profesional (8 pts)

**Completado:**
- `docs/architecture.md` – arquitectura + diagramas Mermaid
- `docs/user_guide.md` – guía de usuario con ejemplos de queries
- `docs/admin_guide.md` – guía de administrador (instalación, operación, troubleshooting)
- `README.md` – índice técnico del proyecto

**Te falta:**
- [ ] Revisar y personalizar las guías con el nombre real de la empresa/sistema.
- [ ] Agregar sección de "Lecciones aprendidas" (el assignment la pide explícitamente).
- [ ] Agregar sección de "Pruebas" con los resultados reales del ETL y queries de ejemplo.

---

## Resumen ejecutivo

| # | Paso | Pts | Estado | Esfuerzo restante |
|---|------|-----|--------|-------------------|
| 1 | Caso de uso | 10 | ✅ 90% | Narrativa del escenario |
| 2 | Modelo + Infraestructura | 10 | ✅ 80% | Tabla de costos |
| 3 | Patrón de diseño LLM | 10 | ✅ 90% | Trade-offs escritos |
| 4 | Docker | 8 | ✅ 95% | `docker compose build` |
| 5 | Orquestación | 8 | ✅ **100%** | — |
| 6 | Arquitectura distribuida | 10 | ✅ 85% | Verificar diagrama |
| 7 | ETL + Sharding | 10 | ✅ **100%** | — |
| 8 | Embeddings + Storage | 6 | ✅ **100%** | — |
| 9 | Reranking + Query Rewriting | 6 | ✅ **95%** | 3 queries de prueba para informe |
| 10 | Multi-Región | 7 | 🔨 30% | Cálculos de costo/latencia |
| 11 | Observabilidad | 7 | ✅ **95%** | Verificar /metrics endpoint |
| 12 | Documentación | 8 | ✅ 80% | Lecciones aprendidas + pruebas |

**Puntaje estimado actual: ~90–94 / 100**
**Con los pendientes (10, 11): ~95–98 / 100**

### Prioridad de pendientes

1. **Media** – Paso 11: completar contadores Prometheus (`.inc()` en los lugares correctos)
2. **Baja** – Pasos 1, 2, 10, 12: redacción/cálculos (tabla costos, narrativa caso de uso, lecciones aprendidas)
3. **Baja** – Paso 9: documentar 3 queries de prueba para el informe
