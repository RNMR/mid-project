#!/usr/bin/env python3
"""
run_etl.py – Entrypoint del Pipeline ETL
=========================================
Paso 7  – Ejecuta el pipeline completo de Ingesta + Sharding.
Paso 8  – Genera embeddings y persiste en el vector store por dominio.

Uso:
    python run_etl.py                       # todos los dominios
    python run_etl.py --domain legal        # solo dominio legal
    python run_etl.py --dry-run             # extrae/chunkea, no carga
    python run_etl.py --reset               # limpia shards antes de ingestar

Dominios disponibles:
    legal          → LEGAL/        (shard_legal)
    technical      → MANUALES/     (shard_technical)
    infrastructure → "DOC WEB"/   (shard_infrastructure)
    operations     → ENCUESTAS/   (shard_operations)
"""

import argparse
import logging
import sys
from pathlib import Path

# El proyecto raíz debe estar en el path para los imports internos
sys.path.insert(0, str(Path(__file__).parent))

from config.settings import LOG_LEVEL
from src.etl.pipeline import ETLPipeline

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(levelname)-8s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("run_etl")

VALID_DOMAINS = ["legal", "technical", "infrastructure", "operations"]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Distributed RAG – Pipeline de Ingesta y Sharding (Pasos 7+8)"
    )
    parser.add_argument(
        "--domain",
        choices=VALID_DOMAINS,
        help="Procesar solo un dominio específico (default: todos)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Extraer y chunkear pero NO generar embeddings ni cargar en vector store",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Eliminar los shards existentes antes de ingestar",
    )
    args = parser.parse_args()

    pipeline = ETLPipeline()

    if args.reset:
        domains_to_reset = [args.domain] if args.domain else None
        logger.info("Reseteando shards...")
        pipeline.reset_shards(domains=domains_to_reset)

    target_domains = [args.domain] if args.domain else None
    mode = "dry-run" if args.dry_run else "completo"
    logger.info(f"Iniciando pipeline ETL – modo={mode} dominios={target_domains or 'todos'}")

    results = pipeline.run(domains=target_domains, dry_run=args.dry_run)

    # ── Resumen ───────────────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("RESUMEN ETL")
    print("=" * 60)
    total_docs   = sum(r.get("docs_processed", 0) for r in results.values())
    total_chunks = sum(r.get("chunks_loaded", 0)  for r in results.values())
    total_gen    = sum(r.get("chunks_generated", 0) for r in results.values())

    for domain, result in results.items():
        status = "✓" if result.get("success") else "✗"
        print(
            f"  {status} {domain:15s} | "
            f"docs={result.get('docs_processed', 0):3d} | "
            f"chunks_gen={result.get('chunks_generated', 0):4d} | "
            f"chunks_cargados={result.get('chunks_loaded', 0):4d}"
        )
        if result.get("errors"):
            for err in result["errors"]:
                print(f"    ERROR: {err}")

    print("-" * 60)
    print(f"  TOTAL: {total_docs} documentos → {total_gen} chunks generados → {total_chunks} cargados")

    if args.dry_run:
        print("  [DRY-RUN] No se cargó nada en el vector store.")

    print("=" * 60)

    all_ok = all(r.get("success", False) for r in results.values())
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
