from django.test import SimpleTestCase
from langchain_core.documents import Document as Chunk
from langchain_core.embeddings import DeterministicFakeEmbedding

from rag_app.rag.index import BM25, HybridIndex, reciprocal_rank_fusion, tokenize


class TokenizeTests(SimpleTestCase):
    def test_keeps_emails_codes_and_drops_trailing_punctuation(self):
        self.assertEqual(
            tokenize("Email security-sos@novatech.io, see NT-OPS-2026-04. Policy."),
            ["email", "security-sos@novatech.io", "see", "nt-ops-2026-04", "policy"],
        )

    def test_hash_prefix_is_ignored(self):
        self.assertEqual(tokenize("#it-emergency"), ["it-emergency"])


class BM25Tests(SimpleTestCase):
    def test_ranks_matching_document_first_and_scores_non_matches_zero(self):
        corpus = [tokenize(t) for t in ["the cat sat", "the dog ran far", "a vpn is required"]]
        scores = BM25(corpus).scores(tokenize("VPN required?"))
        self.assertGreater(scores[2], 0)
        self.assertEqual(scores[:2], [0.0, 0.0])

    def test_idf_never_negative_for_very_common_terms(self):
        corpus = [["policy"], ["policy"], ["policy", "pto"]]
        self.assertTrue(all(s > 0 for s in BM25(corpus).scores(["policy"])))


class RRFTests(SimpleTestCase):
    def test_item_ranked_well_in_both_lists_wins(self):
        # Item 2 is 2nd semantically and 1st by keywords; item 1 is only in one list.
        fused = reciprocal_rank_fusion([[1, 2, 3], [2, 3, 9]], k=60)
        self.assertEqual(max(fused, key=fused.get), 2)
        self.assertAlmostEqual(fused[2], 1 / 62 + 1 / 61)
        self.assertAlmostEqual(fused[1], 1 / 61)
        self.assertAlmostEqual(fused[9], 1 / 63)


class HybridIndexTests(SimpleTestCase):
    def setUp(self):
        texts = [
            "Employees receive 22 days of paid time off.",
            "Report lost laptops to security-sos@novatech.io.",
            "Meal per diem is $65 per day.",
        ]
        self.chunks = [Chunk(page_content=t, metadata={"n": i}) for i, t in enumerate(texts)]
        self.index = HybridIndex(self.chunks, DeterministicFakeEmbedding(size=16))

    def test_exact_keyword_match_is_returned_first(self):
        results = self.index.search("security-sos@novatech.io", k=2)
        self.assertEqual(results[0].chunk.metadata["n"], 1)
        self.assertEqual(results[0].keyword_rank, 1)

    def test_returns_at_most_k_results_sorted_by_score(self):
        results = self.index.search("days", k=2)
        self.assertEqual(len(results), 2)
        self.assertGreaterEqual(results[0].score, results[1].score)

    def test_k_larger_than_corpus(self):
        self.assertEqual(len(self.index.search("anything", k=10)), 3)

    def test_empty_index_is_rejected(self):
        with self.assertRaises(ValueError):
            HybridIndex([], DeterministicFakeEmbedding(size=16))
