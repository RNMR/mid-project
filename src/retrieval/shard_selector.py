"""
shard_selector.py
=================
Paso 3  – Domain Router Pattern: selecciona qué shards consultar.
Paso 9  – Multi-step retrieval: decide si se necesita cross-shard search.

TODO – Implementar:
  1. Clasificador de intención (LLM zero-shot o embeddings de centroide):
       query → legal | technical | infrastructure | operations | multi-domain
  2. Reglas de negocio hard-coded para consultas obvias:
       "artículo" | "ley" | "reglamento" → shard_legal
       "terraform" | "dynamodb" | "api" → shard_technical
       "docker" | "kubernetes" | "aws" → shard_infrastructure
       "encuesta" | "ces" | "satisfacción" → shard_operations
  3. Modo broadcast: si no hay suficiente confianza → consultar todos los shards
     y dejar que el Reranker filtre (Retrieval Cascade Pattern, Paso 3)

Paso 1 – KPI: Shard Selection Accuracy → medir qué % de queries
  se dirigen al shard correcto sin necesidad de broadcast.
"""

from __future__ import annotations

import re

# Palabras clave por dominio para routing basado en reglas
_DOMAIN_KEYWORDS: dict[str, list[str]] = {
    "shard_legal": [
        "ley", "artículo", "reglamento", "decreto", "norma", "legal", "regulación",
        "ministerio", "fiscal", "tributario", "sanción", #"31557", 
    ],
    "shard_technical": [
        "terraform", "dynamodb", "dynamo", "api", "lineamiento", "nomenclatura",
        "git", "azure repos", "base de datos", "estándar", "gti", "microservicio",
        "aws naming", "naming convention",
    ],
    "shard_infrastructure": [
        "docker", "kubernetes", "k8s", "contenedor", "container", "pod",
        "well-architected", "aws", "cloud", "arquitectura cloud", #"gorilla",
    ],
    "shard_operations": [
        "encuesta", "ces", "satisfacción", "apuesta", "casino", "millón city",
        "respuesta", "usuario", "experiencia", "calificación", "nps",
    ],
}


class ShardSelector:
    """Selecciona shards relevantes para una query de usuario.

    Paso 3 – Domain Router Pattern.
    """

    def select(self, query: str, top_k_shards: int = 2) -> list[str]:
        """Retorna lista de shard_names a consultar para la query dada.

        Implementación actual: scoring por palabras clave (heurística).
        TODO: reemplazar con clasificador LLM o embeddings de centroide de shard.
        """
        query_lower = query.lower()
        scores: dict[str, int] = {shard: 0 for shard in _DOMAIN_KEYWORDS}

        for shard, keywords in _DOMAIN_KEYWORDS.items():
            for kw in keywords:
                if re.search(r"\b" + re.escape(kw) + r"\b", query_lower):
                    scores[shard] += 1

        sorted_shards = sorted(scores, key=lambda s: scores[s], reverse=True)

        # Si ningún shard tiene hits → broadcast (todos los shards)
        if scores[sorted_shards[0]] == 0:
            return list(_DOMAIN_KEYWORDS.keys())

        # Solo retornar shards con score > 0 (evita incluir shards irrelevantes)
        matching = [s for s in sorted_shards if scores[s] > 0]
        return matching[:top_k_shards]
