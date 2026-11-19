import io

from django.test import SimpleTestCase

from rag_app.rag.extract import docx_to_markdown

from .helpers import bold_paragraph, handbook_docx, make_docx


def to_markdown(content: bytes) -> str:
    return docx_to_markdown(io.BytesIO(content))


class HeadingTests(SimpleTestCase):
    def test_word_heading_styles(self):
        md = to_markdown(make_docx(lambda d: (d.add_heading("Intro", 1), d.add_heading("Scope", 2))))
        self.assertEqual(md, "# Intro\n\n## Scope")

    def test_bold_numbered_paragraphs_become_headings_with_level_from_numbering(self):
        md = to_markdown(handbook_docx())
        self.assertIn("# 1. Leave Policy", md)
        self.assertIn("## 1.1 Vacation", md)

    def test_bold_sentence_is_not_a_heading(self):
        md = to_markdown(make_docx(lambda d: bold_paragraph(d, "This is important.")))
        self.assertEqual(md, "This is important.")

    def test_partly_bold_paragraph_is_not_a_heading(self):
        def build(d):
            p = d.add_paragraph()
            p.add_run("Stipend:").bold = True
            p.add_run(" every new hire receives $1,200")

        self.assertEqual(to_markdown(make_docx(build)), "Stipend: every new hire receives $1,200")

    def test_hash_at_start_of_text_is_not_treated_as_heading(self):
        md = to_markdown(make_docx(lambda d: d.add_paragraph("#it-emergency is the Slack channel")))
        self.assertEqual(md, "#it-emergency is the Slack channel")


class ParagraphTests(SimpleTestCase):
    def test_list_items_and_whitespace(self):
        def build(d):
            d.add_paragraph("First  point here", style="List Bullet")
            d.add_paragraph("   ")

        self.assertEqual(to_markdown(make_docx(build)), "- First point here")


class TableTests(SimpleTestCase):
    def test_table_to_markdown_keeps_repeated_values(self):
        def build(d):
            table = d.add_table(rows=2, cols=3)
            for cell, text in zip(table.rows[0].cells, ["Plan", "VPN", "2FA"]):
                cell.text = text
            for cell, text in zip(table.rows[1].cells, ["Basic", "Yes", "Yes"]):
                cell.text = text

        self.assertEqual(
            to_markdown(make_docx(build)),
            "| Plan | VPN | 2FA |\n| --- | --- | --- |\n| Basic | Yes | Yes |",
        )

    def test_horizontally_merged_cell_appears_once(self):
        def build(d):
            table = d.add_table(rows=2, cols=3)
            for cell, text in zip(table.rows[0].cells, ["A", "B", "C"]):
                cell.text = text
            merged = table.cell(1, 0).merge(table.cell(1, 1))
            merged.text = "wide"
            table.cell(1, 2).text = "z"

        md = to_markdown(make_docx(build))
        self.assertEqual(md.splitlines()[-1], "| wide | z |  |")

    def test_pipes_in_cells_are_escaped(self):
        def build(d):
            table = d.add_table(rows=2, cols=1)
            table.cell(0, 0).text = "Header"
            table.cell(1, 0).text = "a | b"

        self.assertIn("a \\| b", to_markdown(make_docx(build)))

    def test_single_cell_table_is_unwrapped_as_text(self):
        def build(d):
            cell = d.add_table(rows=1, cols=1).cell(0, 0)
            cell.text = "CRITICAL PROTOCOL"
            cell.add_paragraph("Report within 2 hours.")

        self.assertEqual(to_markdown(make_docx(build)), "CRITICAL PROTOCOL\nReport within 2 hours.")

    def test_content_keeps_document_order(self):
        def build(d):
            d.add_paragraph("before")
            table = d.add_table(rows=2, cols=1)
            table.cell(0, 0).text = "Header"
            table.cell(1, 0).text = "x"
            d.add_paragraph("after")

        md = to_markdown(make_docx(build))
        self.assertLess(md.index("before"), md.index("| x |"))
        self.assertLess(md.index("| x |"), md.index("after"))
