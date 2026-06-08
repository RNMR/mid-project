# Despliegue en AWS EKS — Paso 5

## Pre-requisitos
```bash
brew install eksctl kubectl awscli
aws configure   # Access Key ID + Secret + region: us-east-1
```

---

## Paso 1 — Crear cluster EKS (~15-20 min)
```bash
eksctl create cluster \
  --name rag-cluster \
  --region us-east-1 \
  --nodegroup-name rag-nodes \
  --node-type t3.xlarge \
  --nodes 2 \
  --nodes-min 2 \
  --nodes-max 4 \
  --managed

# Verificar que kubectl apunta al nuevo cluster
kubectl get nodes
```

---

## Paso 2 — ECR: crear repos y subir imágenes

```bash
AWS_ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
REGION=us-east-1

# Login a ECR
aws ecr get-login-password --region $REGION | \
  docker login --username AWS \
  --password-stdin $AWS_ACCOUNT.dkr.ecr.$REGION.amazonaws.com

# Crear repos
aws ecr create-repository --repository-name distributed-rag-api --region $REGION
aws ecr create-repository --repository-name distributed-rag-etl --region $REGION

# Build desde la raíz del proyecto
docker build -f docker/Dockerfile.api \
  -t $AWS_ACCOUNT.dkr.ecr.$REGION.amazonaws.com/distributed-rag-api:latest .

docker build -f docker/Dockerfile.etl \
  -t $AWS_ACCOUNT.dkr.ecr.$REGION.amazonaws.com/distributed-rag-etl:latest .

# Push
docker push $AWS_ACCOUNT.dkr.ecr.$REGION.amazonaws.com/distributed-rag-api:latest
docker push $AWS_ACCOUNT.dkr.ecr.$REGION.amazonaws.com/distributed-rag-etl:latest
```

---

## Paso 3 — Actualizar imagen en el Deployment

Editar `k8s/deployment-api.yaml` línea `image:`:
```yaml
# Cambiar:
image: distributed-rag-api:latest
# Por:
image: <AWS_ACCOUNT>.dkr.ecr.us-east-1.amazonaws.com/distributed-rag-api:latest
```

Idem en `k8s/deployment-ollama.yaml`:
```yaml
# Ollama usa imagen pública — no necesita ECR
image: ollama/ollama:latest   # ya está correcto
```

---

## Paso 4 — Apply de manifiestos

```bash
# Namespace
kubectl apply -f k8s/namespace-and-pvc.yaml

# Secret (solo una vez)
kubectl create secret generic rag-secrets \
  --from-literal=anthropic-api-key=${ANTHROPIC_API_KEY:-placeholder} \
  -n rag

# ConfigMap
kubectl apply -f k8s/configmap.yaml

# Ollama primero — la API lo necesita
kubectl apply -f k8s/deployment-ollama.yaml

# Esperar que Ollama descargue llama3.2 y esté listo (~3-5 min)
kubectl rollout status deployment/ollama -n rag
kubectl wait --for=condition=ready pod -l app=ollama -n rag --timeout=600s

# API + autoescalado + servicio
kubectl apply -f k8s/deployment-api.yaml
kubectl apply -f k8s/hpa.yaml
kubectl apply -f k8s/service.yaml

# ETL como CronJob (re-indexación programada)
kubectl apply -f k8s/cronjob-etl.yaml
```

---

## Paso 5 — Verificar y probar

```bash
# Estado de todos los pods
kubectl get pods -n rag

# Logs de la API
kubectl logs -l app=rag-api -n rag --tail=50

# Port-forward para probar sin Ingress
kubectl port-forward svc/rag-api-service 8000:80 -n rag &

# Test
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{"query": "¿Cuáles son los lineamientos para nombrar tablas en DynamoDB?", "top_k": 5}'

# Métricas Prometheus
curl http://localhost:8000/metrics | grep rag_

# Health check
curl http://localhost:8000/health
```

---

## Paso 6 — Ver logs de retrieval en tiempo real (Paso 9 experimentos)

```bash
# En una terminal: hacer queries
# En otra: ver el pipeline completo
kubectl logs -l app=rag-api -n rag -f | grep -E "\[REWRITE\]|\[SHARDS\]|\[ROUTING\]|\[RRF\]|\[FINAL\]"
```

---

## Limpieza (para no generar costos)

```bash
eksctl delete cluster --name rag-cluster --region us-east-1
```

---

## Arquitectura en EKS

```
Internet → kubectl port-forward (demo) / Ingress nginx (prod)
                        ↓
              rag-api-service (ClusterIP)
                        ↓
            rag-api Pods (2–4, HPA por CPU/memoria)
                        ↓
            ┌───────────┴────────────┐
            ↓                       ↓
    ollama-service            ChromaDB (baked en imagen)
    (llama3.2, CPU)           ← ETL CronJob regenera cada domingo
```

## Decisión: EKS vs alternativas

| Opción | Razón de descarte |
|--------|-------------------|
| AWS Lambda | Cold start ~10s cargando bge-small-en-v1.5 en RAM — viola SLA de 2s |
| Cloud Run | Menos control de anti-affinity multi-AZ; autoscaling menos granular para modelos |
| **EKS** ✅ | HPA por CPU/memoria, pod anti-affinity entre AZs, compatible con Dockerfiles existentes |
