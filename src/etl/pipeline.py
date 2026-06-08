"""
pipeline.py
===========
Paso 7  – Pipeline completo de Ingesta + Sharding.
Paso 8  – Embeddings + Sharded Storage.

Flujo del pipeline por dominio:
  1. Extracción   (PDFExtractor | CSVExtractor)
  2. Limpieza     (TextCleaner)
  3. Chunking     (SmartChunker)
  4. Enriquecimiento (MetadataEnricher)
  5. Carga        (VectorLoader → EmbeddingGenerator + ShardedVectorStore)

Patrón de diseño (Paso 3):
  - Domain Router Pattern: cada dominio se procesa en su shard aislado
  - Sharded Retrieval Pattern: los chunks se almacenan por colección ChromaDB

Este pipeline es el componente central del assignment y el único completamente
implementado en esta fase. Los pasos 3, 5, 9, 10, 11 tienen stubs en
src/retrieval/, src/api/ y src/observability/.
"""

from __future__ import annotations

import logging
from pathlib import Path

from config.settings import DOMAIN_PATHS
from src.etl.extractors.csv_extractor import CSVExtractor
from src.etl.extractors.pdf_extractor import PDFExtractor
from src.etl.loaders.shard_router import ShardRouter
from src.etl.loaders.vector_loader import VectorLoader
from src.etl.transformers.chunker import SmartChunker
from src.etl.transformers.cleaner import TextCleaner
from src.etl.transformers.metadata_enricher import MetadataEnricher

logger = logging.getLogger(__name__)


class ETLPipeline:
    """Orquesta el pipeline completo de ingesta y sharding.

    Paso 7 + 8 del assignment.
    """

    def __init__(self):
        self._router  = ShardRouter()
        self._cleaner = TextCleaner()
        self._chunker = SmartChunker()
        self._enricher = MetadataEnricher()
        self._loader  = VectorLoader()
        self._pdf_ext = PDFExtractor()
        self._csv_ext = CSVExtractor()

    def run(self, domains: list[str] | None = None,
            dry_run: bool = False) -> dict[str, dict]:
        """Ejecuta el pipeline para los dominios indicados.

        Args:
            domains: lista de dominios a procesar; None = todos
            dry_run: si True, extrae y chunkea pero no carga en vector store

        Returns:
            dict domain → {success, docs_processed, chunks_loaded, errors}
        """
        target_domains = domains or list(DOMAIN_PATHS.keys())
        results: dict[str, dict] = {}

        for domain in target_domains:
            logger.info(f"=== Procesando dominio: {domain.upper()} ===")
            results[domain] = self._process_domain(domain, dry_run)

        return results

    def reset_shards(self, domains: list[str] | None = None) -> None:
        """Elimina los shards de los dominios indicados para re-ingesta limpia."""
        target_domains = domains or list(DOMAIN_PATHS.keys())
        for domain in target_domains:
            _, shard = self._router.resolve(DOMAIN_PATHS[domain])
            self._loader.reset_shard(shard)
            logger.info(f"Shard reseteado: {shard}")

    # ── Internals ─────────────────────────────────────────────────────────────

    def _process_domain(self, domain: str, dry_run: bool) -> dict:
        source_dir = DOMAIN_PATHS.get(domain)
        if not source_dir or not source_dir.exists():
            logger.error(f"Directorio no encontrado para dominio '{domain}': {source_dir}")
            return {"success": False, "error": "directory_not_found",
                    "docs_processed": 0, "chunks_loaded": 0}

        files = self._discover_files(source_dir)
        if not files:
            logger.warning(f"No se encontraron archivos en {source_dir}")
            return {"success": True, "docs_processed": 0, "chunks_loaded": 0}

        all_chunks = []
        docs_processed = 0
        errors = []

        for file_path in files:
            try:
                chunks = self._process_file(file_path, domain)
                all_chunks.extend(chunks)
                docs_processed += 1
                logger.info(f"  {file_path.name} → {len(chunks)} chunks")
            except Exception as exc:
                logger.error(f"  Error procesando {file_path.name}: {exc}", exc_info=True)
                errors.append(str(exc))

        chunks_loaded = 0
        if not dry_run and all_chunks:
            chunks_loaded = self._loader.load(all_chunks)
        elif dry_run:
            logger.info(f"[dry-run] {len(all_chunks)} chunks generados, no cargados")
            chunks_loaded = 0

        return {
            "success": len(errors) == 0,
            "docs_processed": docs_processed,
            "chunks_generated": len(all_chunks),
            "chunks_loaded": chunks_loaded,
            "errors": errors,
        }

    def _process_file(self, file_path: Path, domain: str) -> list:
        """Extrae, limpia, chunkea y enriquece un único archivo."""
        _, shard = self._router.resolve(file_path)

        # 1. Extracción
        if file_path.suffix.lower() == ".pdf":
            doc = self._pdf_ext.extract(file_path, domain, shard)
        elif file_path.suffix.lower() == ".csv":
            doc = self._csv_ext.extract(file_path, domain, shard)
        else:
            raise ValueError(f"Tipo de archivo no soportado: {file_path.suffix}")

        # 2. Limpieza
        doc = self._cleaner.clean(doc)

        # 3. Chunking (Paso 7)
        chunks = self._chunker.chunk_document(doc)

        # 4. Enriquecimiento de metadatos (Paso 7)
        chunks = self._enricher.enrich(chunks)

        return chunks

    def _discover_files(self, directory: Path) -> list[Path]:
        supported = {".pdf", ".csv"}
        return [
            f for f in directory.iterdir()
            if f.is_file() and f.suffix.lower() in supported and not f.name.startswith(".")
        ]
