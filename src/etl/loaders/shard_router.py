"""
shard_router.py
===============
Paso 3  – Patrón de diseño: Domain Router Pattern + Sharded Retrieval Pattern.
Paso 7  – Sharding por dominio (obligatorio según assignment).

El ShardRouter determina a qué shard pertenece cada documento
basándose en el directorio fuente (domain-based sharding).

Reglas de asignación:
  LEGAL/     → shard_legal         (documentos regulatorios)
  MANUALES/  → shard_technical     (lineamientos internos)
  DOC WEB/   → shard_infrastructure (guías de infraestructura)
  ENCUESTAS/ → shard_operations    (datos operacionales / encuestas)

En producción (Paso 8), cada shard_* es una colección independiente en
Pinecone (multi-index) o una partición en Qdrant Distributed.
En desarrollo se usa ChromaDB con una colección por shard.
"""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Mapeo directorio → (domain, shard_name)
# Paso 7: "Sharding por dominio (obligatorio)"
_DIR_TO_DOMAIN: dict[str, tuple[str, str]] = {
    "LEGAL":      ("legal",          "shard_legal"),
    "MANUALES":   ("technical",      "shard_technical"),
    "DOC WEB":    ("infrastructure", "shard_infrastructure"),
    "ENCUESTAS":  ("operations",     "shard_operations"),
}


class ShardRouter:
    """Determina dominio y shard a partir del path del documento fuente.

    Paso 3 – Domain Router Pattern: centraliza la lógica de selección de shard
    para que retrieval y escritura usen exactamente las mismas reglas.
    """

    def resolve(self, file_path: Path) -> tuple[str, str]:
        """Retorna (domain, shard_name) para un archivo dado."""
        for dir_name, (domain, shard) in _DIR_TO_DOMAIN.items():
            if dir_name in file_path.parts or dir_name in str(file_path):
                return domain, shard

        logger.warning(f"Archivo fuera de dominios conocidos: {file_path} → fallback 'operations'")
        return "operations", "shard_operations"

    def all_shards(self) -> list[str]:
        return [shard for _, shard in _DIR_TO_DOMAIN.values()]

    def domain_for_shard(self, shard: str) -> str | None:
        for domain, s in _DIR_TO_DOMAIN.values():
            if s == shard:
                return domain
        return None
