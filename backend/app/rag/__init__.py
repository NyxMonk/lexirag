"""LexiRAG retrieval-augmented generation engine.

Pure components (extraction, OCR, language detection, chunking, BM25, fusion,
prompting) live here and do not depend on the API layer. Model-backed components
(embeddings, reranking, LLM providers) are lazily initialised singletons.
"""
