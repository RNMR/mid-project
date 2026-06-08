# Guía de Administrador – Distributed RAG System
## Paso 12 – Documentación Final: Guía de Administrador

---

## Arquitectura de componentes

```
run_etl.py
  └── ETLPipeline (src/etl/pipeline.py)
        ├── PDFExtractor / CSVExtractor     → Paso 7: extracción
        ├── TextCleaner                     → Paso 7: normalización
        ├── SmartChunker                    → Paso 7: chunking
        ├── MetadataEnricher                → Paso 7: metadatos
        └── VectorLoader
              ├── EmbeddingGenerator        → Paso 8: BGE embeddings
              └── ShardedVectorStore        → Paso 8: ChromaDB shards

src/api/main.py (FastAPI)
  └── MultiIndexRetriever
        ├── QueryRewriter                   → Paso 9: query rewriting
        ├── ShardSelector                   → Paso 3: domain routing
        ├── ShardedVectorStore.query()      → Paso 3: retrieval
        └── Reranker                        → Paso 9: cross-encoder
```

---

## Variables de entorno

| Variable | Requerida | Default | Descripción |
|----------|-----------|---------|-------------|
| `ANTHROPIC_API_KEY` | Para query/respuesta | — | Clave API de Claude |
| `VECTOR_BACKEND` | No | `chromadb` | `chromadb` \| `pinecone` \| `qdrant` |
| `PINECONE_API_KEY` | Si backend=pinecone | — | Clave Pinecone |
| `LOG_LEVEL` | No | `INFO` | `DEBUG` \| `INFO` \| `WARNING` |
| `METRICS_PORT` | No | `9090` | Puerto Prometheus |
| `AWS_REGION` | No | `us-east-1` | Región primaria |
| `REPLICA_REGIONS` | No | `us-west-2` | Regiones réplica (CSV) |

---

## Estructura de datos en ChromaDB

Cada shard es una colección ChromaDB con:
- **ID**: `{doc_stem}_{uuid8}` (ej. `ley_n_31557_a3f2bc91`)
- **Document**: texto del chunk
- **Embedding**: vector float32[384] (BGE, cosine)
- **Metadata**:
  ```json
  {
    "source_file": "Ley N° 31557 2095517-1.pdf",
    "domain": "legal",
    "shard": "shard_legal",
    "file_type": ".pdf",
    "page_num": 3,
    "chunk_index": 12,
    "total_chunks_in_doc": 47,
    "ingested_at": "2026-05-31T10:00:00Z",
    "language_hint": "es",
    "token_approx": 487,
    "char_count": 2341
  }
  ```

---

## Operaciones de mantenimiento

### Re-indexar un dominio específico
```bash
python run_etl.py --reset --domain technical
```

### Ver estadísticas del vector store
```bash
python -c "
from src.embeddings.vector_store import ShardedVectorStore
store = ShardedVectorStore()
for shard, count in store.stats().items():
    print(f'{shard}: {count} chunks')
"
```

### Agregar un nuevo documento
1. Copiar el PDF/CSV al directorio del dominio correspondiente
2. Ejecutar `python run_etl.py --domain <dominio>`
3. Los chunks nuevos se upsertean sin duplicar los existentes

### Modificar el tamaño de chunk
En `config/settings.py`:
```python
CHUNK_SIZE_TOKENS    = 512   # ajustar según modelo LLM target
CHUNK_OVERLAP_TOKENS = 50    # 10% del chunk size es una buena regla
```
Luego re-indexar: `python run_etl.py --reset`

---

## Migración a Pinecone (Paso 8 – producción)

1. Instalar cliente: `pip install pinecone-client`
2. Crear índices en Pinecone (uno por shard):
   ```
   shard_legal, shard_technical, shard_infrastructure, shard_operations
   dimension=384, metric=cosine
   ```
3. Cambiar en `.env`:
   ```
   VECTOR_BACKEND=pinecone
   PINECONE_API_KEY=...
   ```
4. Implementar `PineconeVectorStore` siguiendo la interfaz de `ShardedVectorStore`
5. Re-indexar todos los dominios

---

## Monitoreo – Métricas clave (Paso 11)

| Métrica | Alerta si |
|---------|-----------|
| `rag_query_latency_seconds{p99}` | > SLA del dominio |
| `rag_shard_errors_total` | > 0 en 5 min |
| `rag_cache_hits_total / total_queries` | < 20% (semantic cache ineficiente) |
| `rag_chunk_count` | Baja inesperadamente (chunks eliminados) |

Evaluación RAGAS por dominio (Paso 11):
```bash
# TODO: ejecutar evaluación RAGAS mensualmente
# ragas evaluate --dataset eval_legal.json --metrics faithfulness,context_recall
```

---

## Escalado en Kubernetes (Paso 5)

```yaml
# HPA para el API pod
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
spec:
  scaleTargetRef:
    name: rag-api
  minReplicas: 2
  maxReplicas: 10
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: 60
```

```yaml
# Pod Anti-Affinity: distribuir réplicas entre zonas (Paso 5)
affinity:
  podAntiAffinity:
    preferredDuringSchedulingIgnoredDuringExecution:
      - weight: 100
        podAffinityTerm:
          topologyKey: topology.kubernetes.io/zone
```

---

## Costos estimados (Paso 2 – justificación de infraestructura)

| Componente | Dev (ChromaDB local) | Prod (Pinecone) |
|------------|---------------------|-----------------|
| Embeddings | $0 (BGE local) | $0 (BGE) o ~$0.10/M tokens (OpenAI) |
| Vector store | $0 | ~$70/mes (Pinecone Starter) |
| LLM (Claude) | ~$0.003/query | ~$0.003/query |
| API hosting | $0 (local) | ~$50/mes (Cloud Run) |
| **Total /1000 queries** | ~$3 | ~$6–$10 |

**Costo por 1000 queries (Paso 1 KPI)**: aprox. $3–10 dependiendo del volumen
y del modelo de embeddings seleccionado en producción.
