"""Hybrid retrieval: semantic (embedding) search + keyword (BM25) search, fused with RRF.

Why both?
- Embeddings find passages with the same *meaning* ("time off" ~ "vacation days")
  but are weak on exact tokens such as codes, names and emails.
- BM25 finds exact *words* ("NT-OPS-2026-04", "security-sos@novatech.io") but misses
  paraphrases.
Reciprocal Rank Fusion (RRF) merges the two ranked lists using only the *ranks*,
so we never have to compare a cosine similarity with a BM25 score (different scales).
"""

import math
import re
from collections import Counter
from dataclasses import dataclass

from langchain_core.documents import Document as Chunk
from langchain_core.embeddings import Embeddings
from langchain_core.vectorstores import InMemoryVectorStore

# Words, plus tokens joined by . _ - @ so that emails, versions and codes stay whole:
# "security-sos@novatech.io", "nt-ops-2026-04", "2.1". Trailing punctuation is dropped.
_TOKEN_RE = re.compile(r"[a-z0-9]+(?:[._@-][a-z0-9]+)*")

# Standard constant from the original RRF paper (Cormack et al., 2009).
RRF_K = 60


def tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


class BM25:
    """Okapi BM25 keyword scoring (the ranking function used by Lucene/Elasticsearch).

    Small enough to own: ~25 lines, no dependency. It uses Lucene's IDF variant,
    log(1 + (N - df + 0.5) / (df + 0.5)), which is never negative even when a word
    appears in most chunks (a known quirk of the classic formula on small corpora).
    """

    def __init__(self, corpus: list[list[str]], k1: float = 1.5, b: float = 0.75):
        self.k1, self.b = k1, b
        self.term_freqs = [Counter(tokens) for tokens in corpus]
        self.lengths = [len(tokens) for tokens in corpus]
        self.avg_length = (sum(self.lengths) / len(corpus)) if corpus else 0.0
        doc_freq = Counter(term for tokens in corpus for term in set(tokens))
        n = len(corpus)
        self.idf = {
            term: math.log(1 + (n - df + 0.5) / (df + 0.5)) for term, df in doc_freq.items()
        }

    def scores(self, query_tokens: list[str]) -> list[float]:
        terms = [t for t in set(query_tokens) if t in self.idf]
        result = []
        for tf, length in zip(self.term_freqs, self.lengths):
            norm = self.k1 * (1 - self.b + self.b * length / (self.avg_length or 1))
            result.append(
                sum(self.idf[t] * tf[t] * (self.k1 + 1) / (tf[t] + norm) for t in terms if t in tf)
            )
        return result


def reciprocal_rank_fusion(rankings: list[list[int]], k: int = RRF_K) -> dict[int, float]:
    """score(item) = sum over lists of 1 / (k + rank). Ranks start at 1."""
    fused: dict[int, float] = {}
    for ranking in rankings:
        for rank, item in enumerate(ranking, start=1):
            fused[item] = fused.get(item, 0.0) + 1.0 / (k + rank)
    return fused


@dataclass(frozen=True)
class SearchResult:
    chunk: Chunk
    score: float  # fused RRF score
    vector_rank: int | None  # 1 = best semantic match, None = not in semantic top list
    keyword_rank: int | None  # 1 = best BM25 match, None = no keyword overlap


class HybridIndex:
    """An immutable search index over a fixed list of chunks.

    Built once and then only read, so it is safe to share between request threads;
    when documents change, a new index is built and swapped in.
    """

    def __init__(self, chunks: list[Chunk], embeddings: Embeddings):
        if not chunks:
            raise ValueError("Cannot build an index without chunks.")
        self.chunks = chunks
        # Exact cosine-similarity search in memory. For thousands of chunks this is
        # milliseconds; a larger corpus would swap in FAISS/pgvector behind the same
        # LangChain VectorStore interface.
        self._vectors = InMemoryVectorStore.from_texts(
            [c.page_content for c in chunks],
            embeddings,
            metadatas=[{"position": i} for i in range(len(chunks))],
        )
        self._bm25 = BM25([tokenize(c.page_content) for c in chunks])

    def search(self, query: str, k: int = 5, candidates: int = 20) -> list[SearchResult]:
        candidates = min(max(candidates, k), len(self.chunks))

        vector_hits = self._vectors.similarity_search_with_score(query, k=candidates)
        vector_ranking = [doc.metadata["position"] for doc, _ in vector_hits]

        bm25_scores = self._bm25.scores(tokenize(query))
        keyword_ranking = sorted(
            (i for i, score in enumerate(bm25_scores) if score > 0),
            key=lambda i: bm25_scores[i],
            reverse=True,
        )[:candidates]

        fused = reciprocal_rank_fusion([vector_ranking, keyword_ranking])
        best = sorted(fused, key=fused.get, reverse=True)[:k]
        return [
            SearchResult(
                chunk=self.chunks[i],
                score=fused[i],
                vector_rank=_rank_of(i, vector_ranking),
                keyword_rank=_rank_of(i, keyword_ranking),
            )
            for i in best
        ]


def _rank_of(item: int, ranking: list[int]) -> int | None:
    return ranking.index(item) + 1 if item in ranking else None
