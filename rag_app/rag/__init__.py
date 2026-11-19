"""The retrieval-augmented generation pipeline, independent of Django.

extract.py   .docx -> Markdown
chunking.py  Markdown -> section-aware chunks
index.py     HybridIndex: embeddings + BM25, fused with Reciprocal Rank Fusion
qa.py        prompt + LLM chain that produces a cited, grounded answer

`rag_app/services.py` connects these pieces to the Django models.
"""
