# Guía de Usuario – Distributed RAG System
## Paso 12 – Documentación Final: Guía de Usuario

---

## ¿Qué es este sistema?

Sistema de pregunta-respuesta inteligente que permite consultar en lenguaje natural
los documentos de la organización: normativa legal, lineamientos técnicos,
guías de infraestructura y datos de encuestas de experiencia.

El sistema usa **Retrieval-Augmented Generation (RAG)** con **sharding por dominio**:
cada tipo de documento vive en un índice vectorial independiente (shard),
lo que garantiza búsqueda rápida y precisa sin mezclar contextos.

---

## Inicio rápido

### 1. Instalar dependencias

```bash
cd "mid project"
pip install -r requirements.txt
```

### 2. Configurar credenciales

```bash
cp .env.example .env
# Editar .env y agregar ANTHROPIC_API_KEY=sk-ant-...
```

### 3. Ejecutar el ETL (indexar los documentos)

```bash
# Indexar todos los dominios
python run_etl.py

# Solo un dominio específico
python run_etl.py --domain legal
python run_etl.py --domain technical
python run_etl.py --domain infrastructure
python run_etl.py --domain operations

# Ver qué se generaría sin guardar
python run_etl.py --dry-run

# Re-indexar desde cero
python run_etl.py --reset
```

# LEVANTA OLLAMA
ollama serve

### 4. Iniciar la API

```bash
python -m src.api.main
# API disponible en http://localhost:8000
# Documentación: http://localhost:8000/docs
```

### 5. Hacer una consulta

```bash
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{"query": "¿Cuáles son los lineamientos para nombrar tablas en DynamoDB?"}'
```

---

## Casos de uso por dominio

### Dominio Legal (`shard_legal`)
**Documentos**: Ley N° 31557 (Perú)

Ejemplos de consultas:
- "¿Qué dice el Artículo 5 de la ley 31557?"
- "¿Cuáles son las sanciones establecidas en la normativa?"
- "¿Cuál es el ámbito de aplicación de la ley?"

### Dominio Técnico (`shard_technical`)
**Documentos**: Lineamientos GTI (APIs, BD, DynamoDB, Terraform, Git, AWS)

Ejemplos de consultas:
- "¿Cómo debo nombrar los objetos en DynamoDB?"
- "¿Cuáles son las buenas prácticas para APIs REST según el lineamiento GTI?"
- "¿Qué convenciones de nomenclatura se deben usar en servicios AWS?"
- "¿Cómo se estructura el control de versiones con Git y Azure Repos?"

### Dominio Infraestructura (`shard_infrastructure`)
**Documentos**: Docker Deployment Guide, Gorilla Guide to Kubernetes, AWS Well-Architected

Ejemplos de consultas:
- "¿Cómo desplegar una aplicación con Docker multi-stage?"
- "¿Qué es un Pod en Kubernetes y cómo se configura un Deployment?"
- "¿Cuáles son los 5 pilares del AWS Well-Architected Framework?"

### Dominio Operaciones (`shard_operations`)
**Documentos**: Encuestas CES (apuestas deportivas, casino, Millón City)

Ejemplos de consultas:
- "¿Cuáles son los principales problemas de experiencia en apuestas deportivas?"
- "¿Qué dice la encuesta sobre la facilidad de uso del casino online?"
- "¿Cuál es el sentimiento predominante en las respuestas de enero 2026?"

---

## Verificar que el ETL funcionó correctamente

```bash
# Ver estadísticas de chunks por shard
curl http://localhost:8000/shards
```

Respuesta esperada después de un ETL exitoso:
```json
{
  "shards": {
    "shard_legal": 45,
    "shard_technical": 312,
    "shard_infrastructure": 278,
    "shard_operations": 18
  }
}
```

---

## Con Docker

```bash
# Construir imágenes
docker compose -f docker/docker-compose.yml build

# Correr ETL
docker compose -f docker/docker-compose.yml run etl

# Iniciar API
docker compose -f docker/docker-compose.yml up api

# Con observabilidad (Prometheus)
docker compose -f docker/docker-compose.yml --profile observability up
```

---

## Solución de problemas comunes

| Problema | Causa probable | Solución |
|----------|---------------|----------|
| `0 chunks` en un dominio | PDFs escaneados sin OCR | Verificar log: "páginas sin texto detectable" |
| Error de API key | `.env` no configurado | Copiar `.env.example` y agregar clave |
| `ModuleNotFoundError` | Dependencias no instaladas | `pip install -r requirements.txt` |
| Respuesta vacía en `/query` | ETL no ejecutado | Correr `python run_etl.py` primero |
