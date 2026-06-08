# Arquitectura Distribuida RAG con Sharding
## Proyecto 9 – Distributed RAG Architecture (Sharded Vector Stores)

---

## Paso 3 – Patrón de Diseño LLM

### Patrones implementados

| Patrón | Estado | Archivo |
|--------|--------|---------|
| **Sharded Retrieval Pattern** (obligatorio) | Implementado (ETL) | `src/etl/loaders/shard_router.py` |
| **Multi-Index Retrieval Pattern** | Stub conectado | `src/retrieval/multi_index_retriever.py` |
| **Domain Router Pattern** | Implementado | `src/retrieval/shard_selector.py` |
| **Query Rewriting Pattern** | Stub | `src/retrieval/query_rewriter.py` |
| **Reranking Pattern** | Stub (RRF implementado) | `src/retrieval/reranker.py` |
| **Retrieval Cascade Pattern** | En ShardSelector (broadcast) | `src/retrieval/shard_selector.py` |

---

## Paso 6 – Diagrama de Arquitectura Completa Distribuida

```mermaid
graph TB
    subgraph Ingesta["🔄 Pipeline ETL (Paso 7+8) – IMPLEMENTADO"]
        SRC_L[LEGAL/\nLey N° 31557]
        SRC_T[MANUALES/\nLineamientos GTI]
        SRC_I[DOC WEB/\nDocker·K8s·AWS]
        SRC_O[ENCUESTAS/\nCES·Encuestas]

        EXT[Extractors\nPDFExtractor · CSVExtractor]
        CLN[TextCleaner\nnormalización + deruido]
        CHK[SmartChunker\nsección-based + sliding window]
        ENR[MetadataEnricher\ntimestamp · idioma · índices]

        ROUTER[ShardRouter\nDomain Router Pattern]

        EMB[EmbeddingGenerator\nBGE bge-small-en-v1.5]

        SRC_L & SRC_T & SRC_I & SRC_O --> EXT
        EXT --> CLN --> CHK --> ENR --> ROUTER --> EMB
    end

    subgraph Shards["🗄️ Sharded Vector Store (Paso 8) – ChromaDB local / Pinecone en prod"]
        S_LEG[(shard_legal\nLegal)]
        S_TEC[(shard_technical\nTechnical)]
        S_INF[(shard_infrastructure\nInfrastructure)]
        S_OPS[(shard_operations\nOperations)]
    end

    EMB --> S_LEG & S_TEC & S_INF & S_OPS

    subgraph Retrieval["🔍 Retrieval Pipeline (Paso 3+9) – Stubs"]
        QRW[QueryRewriter\nClaude · multi-step]
        SEL[ShardSelector\nDomain Router]
        MIR[MultiIndexRetriever\nParalelo · ThreadPool]
        RNK[Reranker\nCross-encoder · RRF]
        LLM[Claude API\nGeneración de respuesta]
    end

    USR((Usuario)) -->|query| QRW
    QRW --> SEL --> MIR
    MIR -->|consulta paralela| S_LEG & S_TEC & S_INF & S_OPS
    S_LEG & S_TEC & S_INF & S_OPS -->|top-k chunks| RNK
    RNK -->|chunks re-ordenados| LLM
    LLM -->|respuesta| USR

    subgraph API["🌐 API Layer (Paso 5) – FastAPI"]
        REST[POST /query\nGET /health\nGET /metrics]
    end

    USR <--> REST <--> QRW

    subgraph Obs["📊 Observabilidad (Paso 11) – Stub"]
        PROM[Prometheus\n/metrics]
        LOG[structlog\nJSON structured]
    end

    REST --> PROM & LOG

    style Ingesta fill:#e8f5e9,stroke:#43a047
    style Shards fill:#e3f2fd,stroke:#1e88e5
    style Retrieval fill:#fff3e0,stroke:#fb8c00
    style API fill:#f3e5f5,stroke:#8e24aa
    style Obs fill:#fce4ec,stroke:#e53935
```

---

## Paso 7 – Diseño del Pipeline de Ingesta + Sharding

### Flujo por tipo de documento

```mermaid
flowchart LR
    PDF([PDF]) --> PE[PDFExtractor\npdfplumber\npágina por página]
    CSV([CSV Qualtrics]) --> CE[CSVExtractor\npandas\nfila 1=headers ES\nskip filas 0,2]

    PE & CE --> CL[TextCleaner\n- NFC normalize\n- remove control chars\n- collapse whitespace]

    CL --> SC{SmartChunker}
    SC -->|secciones detectadas| SEC[SectionChunker\nArtículo / Capítulo\nSección / Chapter]
    SC -->|sin estructura| SLD[SlidingWindowChunker\n512 tokens, 50 overlap]
    SEC & SLD --> ME[MetadataEnricher\ningested_at, lang, index]
    ME --> SR[ShardRouter\ndirectorio → dominio]
    SR --> EG[EmbeddingGenerator\nBAAI/bge-small-en-v1.5\nbatch=32, L2-norm]
    EG --> VS[ShardedVectorStore\nChromaDB collections\ncosine similarity]
```

### Criterio de Sharding (Paso 7 – obligatorio)

| Directorio fuente | Dominio | Shard ChromaDB | Tipo de chunking |
|-------------------|---------|----------------|------------------|
| `LEGAL/` | legal | `shard_legal` | Section (Artículo/Título) |
| `MANUALES/` | technical | `shard_technical` | Section + Sliding fallback |
| `DOC WEB/` | infrastructure | `shard_infrastructure` | Section (Chapter) + Sliding |
| `ENCUESTAS/` | operations | `shard_operations` | Sliding (20 rows/chunk) |

---

## Paso 8 – Embeddings y Vector Storage

### Modelo seleccionado: BAAI/bge-small-en-v1.5

| Criterio | Valor |
|----------|-------|
| Dimensiones | 384 |
| Costo inferencia | $0 (local) |
| Latencia por batch de 32 | ~50ms CPU / ~5ms GPU |
| Recall MTEB (avg) | 0.621 |
| Normalización | L2 → cosine similarity |

### Migración a producción (Paso 2 – infraestructura)

```
Dev:  ChromaDB local (PersistentClient)
      ↓ cambiar VECTOR_BACKEND=pinecone en .env
Prod: Pinecone (multi-index = un índice por shard)
      ↓ Paso 10: replicación multi-región
Geo:  Pinecone pods en us-east-1 (primary) + eu-west-1 (réplica)
```

---

## Paso 10 – Optimización Multi-Región y Alta Disponibilidad

### Topología de replicación

```mermaid
graph LR
    CLI[Cliente] --> GLB[Global Load Balancer\ngeo-routing]
    GLB -->|us-east-1| P1[API Pod\nus-east-1]
    GLB -->|eu-west-1| P2[API Pod\neu-west-1]

    P1 --> VS1[(Vector Store\nus-east-1\nprimary)]
    P2 --> VS2[(Vector Store\neu-west-1\nréplica)]

    VS1 <-->|replicación activa/pasiva| VS2

    P1 & P2 --> CACHE[Redis Semantic Cache\nTTL 1h]

    P1 -->|circuit breaker| CB1{Shard disponible?}
    CB1 -->|no| FB[Fallback: shard alternativo]
    CB1 -->|sí| VS1
```

### TODOs Paso 10
- [ ] Configurar replicación activa/pasiva en Pinecone (primary → réplica)
- [ ] Implementar geo-balancing en Route53 / Cloud DNS
- [ ] Circuit breaker: si shard no responde en 500ms → fallback a otro shard
- [ ] Semantic caching: Redis con hash de embedding como key, TTL 3600s
- [ ] Calcular latencia cross-region: us-east-1 → eu-west-1 (~75ms RTT)

---

## Paso 1 – KPIs por Dominio

| KPI | Legal | Technical | Infrastructure | Operations |
|-----|-------|-----------|----------------|------------|
| Retrieval Accuracy target | 95% | 90% | 85% | 88% |
| Latencia p99 (ms) | 2000 | 1500 | 1500 | 500 |
| Reranking Quality min | 0.85 | 0.80 | 0.75 | 0.78 |
| Shard Selection Accuracy | > 98% | > 95% | > 92% | > 90% |

---

## Trade-offs técnicos (Paso 3)

| Decisión | Alternativa | Trade-off |
|----------|-------------|-----------|
| BGE-small (384d) local | Azure OpenAI ada-002 (1536d) | Menor calidad vs costo $0 y sin latencia de red |
| ChromaDB (dev) → Pinecone (prod) | Qdrant Distributed | Pinecone managed + multi-index nativo; Qdrant más flexible en self-hosted |
| SectionChunker primero | Solo SlidingWindow | Mejor coherencia semántica; riesgo de secciones muy largas (mitigado con split) |
| Serverless (Cloud Run) | Kubernetes | Cloud Run: zero cold-start en prod; K8s: más control GPU para reranker |
