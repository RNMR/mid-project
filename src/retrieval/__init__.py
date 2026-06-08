"""
Módulo de retrieval distribuido (Pasos 3, 9 del assignment).

Componentes:
  ShardSelector        – selecciona qué shards consultar para una query
  MultiIndexRetriever  – consulta múltiples shards en paralelo y fusiona
  QueryRewriter        – reformula la query usando LLM (Claude)
  Reranker             – ordena resultados con cross-encoder

Estado: STUBS con TODOs detallados.
El ETL (Paso 7+8) está completamente implementado; estos módulos
son el siguiente paso de desarrollo.
"""
