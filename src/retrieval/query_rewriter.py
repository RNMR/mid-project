"""
query_rewriter.py
=================
Paso 9 – Query Rewriting: reformulación multi-step con Ollama (local, gratis).

Estrategias implementadas:
  1. Reformulación simple: genera 3 variantes más específicas de la query
  2. Reroll: si retrieve() no retorna resultados, se puede llamar rewrite() de nuevo
     con instrucciones más generales (implementar en MultiIndexRetriever)

Experimentos comparativos requeridos (Paso 9):
  - Query original vs reformulada: medir Recall@K en cada shard
  - Con / sin query rewriting: comparar Retrieval Accuracy (Paso 1 KPI)

Requisito: Ollama corriendo localmente
  brew install ollama && ollama pull llama3.2
"""

from __future__ import annotations

import json
import logging

from config.settings import OLLAMA_MODEL

logger = logging.getLogger(__name__)

_REWRITE_SYSTEM_PROMPT = """Eres un experto en recuperación de información.
Tu tarea es reformular la consulta del usuario para mejorar la búsqueda semántica
en una base de conocimiento que contiene:
  - Documentos legales y regulatorios (Perú)
  - Lineamientos técnicos de TI (APIs, bases de datos, cloud, infraestructura)
  - Guías de Docker, Kubernetes y creacion de aquitecturas AWS
  - Encuestas de experiencia de usuario (CES, apuestas deportivas, casino)

Genera exactamente 3 reformulaciones de la consulta, más específicas y ricas en
términos técnicos o legales según el dominio detectado.
Responde SOLO con JSON: {"rewritten_queries": ["...", "...", "..."]}"""


class QueryRewriter:
    """Reformula queries usando Ollama (LLM local) para mejorar retrieval.

    Paso 9 – Query Rewriting Pattern.
    """

    def rewrite(self, query: str) -> list[str]:
        """Retorna la query original + 3 variantes reformuladas.

        Si Ollama no está disponible, retorna solo la query original (pass-through).
        """
        try:
            import ollama
            response = ollama.chat(
                model=OLLAMA_MODEL,
                messages=[
                    {"role": "system", "content": _REWRITE_SYSTEM_PROMPT},
                    {"role": "user", "content": query},
                ],
                options={"temperature": 0.3},
            )
            text = response["message"]["content"].strip()

            # Extraer el JSON de la respuesta (a veces el LLM añade texto extra)
            start = text.find("{")
            end = text.rfind("}") + 1
            if start >= 0 and end > start:
                data = json.loads(text[start:end])
                rewrites = data.get("rewritten_queries", [])
                if rewrites:
                    logger.info(f"Query rewriting: {len(rewrites)} variantes generadas")
                    return [query] + rewrites

        except ImportError:
            logger.warning("ollama no instalado – usar: pip install ollama")
        except Exception as exc:
            logger.warning(f"Query rewriting falló ({exc}) – usando query original")

        return [query]
