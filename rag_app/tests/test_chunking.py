from django.test import SimpleTestCase

from rag_app.rag.chunking import chunk_markdown, is_markdown_table, split_table

TABLE = "| Name | Role |\n| --- | --- |\n" + "\n".join(f"| person{i} | role{i} |" for i in range(40))


class ChunkMarkdownTests(SimpleTestCase):
    def test_section_path_follows_heading_hierarchy(self):
        md = "# 1. Policy\n\n## 1.1 Leave\n\nLeave text.\n\n## 1.2 Travel\n\nTravel text.\n\n# 2. Other\n\nOther text."
        chunks = chunk_markdown(md)
        self.assertEqual(
            [c.metadata["section"] for c in chunks],
            ["1. Policy > 1.1 Leave", "1. Policy > 1.2 Travel", "2. Other"],
        )
        self.assertEqual(chunks[0].page_content, "Section: 1. Policy > 1.1 Leave\nLeave text.")

    def test_text_before_first_heading_has_no_section(self):
        chunks = chunk_markdown("Preamble.\n\n# Title\n\nBody.")
        self.assertEqual(chunks[0].page_content, "Preamble.")
        self.assertEqual(chunks[0].metadata["section"], "")

    def test_headings_without_body_produce_no_chunks(self):
        self.assertEqual(chunk_markdown("# A\n\n## B"), [])

    def test_hash_word_is_text_not_heading(self):
        chunks = chunk_markdown("#it-emergency channel")
        self.assertEqual(chunks[0].page_content, "#it-emergency channel")

    def test_long_paragraph_is_split_within_size(self):
        long_paragraph = " ".join(f"Sentence number {i} is here." for i in range(200))
        chunks = chunk_markdown(long_paragraph, chunk_size=300, chunk_overlap=50)
        self.assertGreater(len(chunks), 5)
        self.assertTrue(all(len(c.page_content) <= 300 for c in chunks))

    def test_metadata_is_copied_to_every_chunk(self):
        chunks = chunk_markdown("# A\n\ntext\n\n" + TABLE, chunk_size=200, metadata={"document_id": 7})
        self.assertTrue(all(c.metadata["document_id"] == 7 for c in chunks))

    def test_tables_are_separate_chunks_flagged_as_tables(self):
        chunks = chunk_markdown("Intro.\n\n| a | b |\n| --- | --- |\n| 1 | 2 |\n\nOutro.")
        self.assertEqual([c.metadata["is_table"] for c in chunks], [False, True, False])


class TableSplitTests(SimpleTestCase):
    def test_detects_markdown_tables(self):
        self.assertTrue(is_markdown_table("| a |\n| --- |\n| 1 |"))
        self.assertFalse(is_markdown_table("INTERNAL | MANUAL\nsecond line"))

    def test_small_table_is_kept_whole(self):
        self.assertEqual(split_table("| a |\n| --- |\n| 1 |", 800), ["| a |\n| --- |\n| 1 |"])

    def test_large_table_split_by_rows_with_header_repeated(self):
        parts = split_table(TABLE, max_chars=200)
        self.assertGreater(len(parts), 1)
        for part in parts:
            self.assertTrue(part.startswith("| Name | Role |\n| --- | --- |\n| person"))
            self.assertLessEqual(len(part), 200)
        all_rows = [line for part in parts for line in part.splitlines()[2:]]
        self.assertEqual(all_rows, TABLE.splitlines()[2:])  # nothing lost or duplicated
