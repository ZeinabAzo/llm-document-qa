"""Convert a .docx file into Markdown text.

Why Markdown? It keeps the document *structure* (headings, lists, tables) in plain
text. The chunker uses the headings to label every chunk with its section, and the
LLM reads Markdown tables well.
"""

import re
from typing import BinaryIO

import docx
from docx.table import Table
from docx.text.paragraph import Paragraph

# "2.1 Paid Time Off" -> level 2, "3. Security" -> level 1.
_NUMBERED_HEADING = re.compile(r"^(\d+(?:\.\d+)*)\.?\s+\S")
# A paragraph longer than this is body text even if it is bold.
_MAX_HEADING_CHARS = 120


def docx_to_markdown(source: str | BinaryIO) -> str:
    """Return the document body as Markdown, in reading order.

    `source` is a path or a binary file object. Page headers/footers are skipped
    on purpose: they repeat on every page and add noise to retrieval.
    """
    document = docx.Document(source)
    blocks: list[str] = []
    for item in document.iter_inner_content():
        block = _table_to_markdown(item) if isinstance(item, Table) else _paragraph_to_markdown(item)
        if block:
            blocks.append(block)
    return "\n\n".join(blocks)


def _clean(text: str) -> str:
    """Collapse whitespace (including non-breaking spaces) into single spaces."""
    return " ".join(text.replace("\xa0", " ").split())


def _paragraph_to_markdown(paragraph: Paragraph) -> str:
    text = _clean(paragraph.text)
    if not text:
        return ""
    level = _heading_level(paragraph, text)
    if level:
        return f"{'#' * level} {text}"
    style = paragraph.style.name if paragraph.style is not None else ""
    if style.startswith("List"):
        return f"- {text}"
    return text


def _heading_level(paragraph: Paragraph, text: str) -> int | None:
    """Detect headings, including "fake" ones.

    Many real documents never use Word's Heading styles; authors just make a short
    line bold (the sample handbook does exactly this). So we accept either:
      1. a "Heading N" / "Title" style, or
      2. a short paragraph whose text is entirely bold.
    The level comes from the style number, else from numbering like "2.1", else 1.
    """
    style = paragraph.style.name if paragraph.style is not None else ""
    if style == "Title":
        return 1
    if style.startswith("Heading"):
        suffix = style.removeprefix("Heading").strip()
        return min(int(suffix), 6) if suffix.isdigit() else 1

    runs_with_text = [run for run in paragraph.runs if run.text.strip()]
    looks_like_heading = (
        runs_with_text
        and len(text) <= _MAX_HEADING_CHARS
        and all(run.bold for run in runs_with_text)
        and not text.endswith((".", ":", ";", ","))
    )
    if not looks_like_heading:
        return None
    match = _NUMBERED_HEADING.match(text)
    return min(match.group(1).count(".") + 1, 6) if match else 1


def _cell_text(cell) -> str:
    # Markdown tables are one line per row, so newlines become spaces and pipes are escaped.
    return _clean(cell.text).replace("|", "\\|")


def _table_to_markdown(table: Table) -> str:
    rows: list[list[str]] = []
    for row in table.rows:
        cells, seen = [], set()
        for cell in row.cells:
            # A horizontally merged cell is returned once per grid column it spans,
            # always as the *same* underlying XML element. Compare identity, not text,
            # so two different cells that both say "Yes" are both kept.
            if id(cell._tc) in seen:
                continue
            seen.add(id(cell._tc))
            cells.append(_cell_text(cell))
        if any(cells):
            rows.append(cells)

    if not rows:
        return ""

    # A one-cell table is a layout box (a banner or a "warning" callout), not data.
    if len(rows) == 1 and len(rows[0]) == 1:
        return "\n".join(_clean(p.text) for p in table.cell(0, 0).paragraphs if p.text.strip())

    width = max(len(row) for row in rows)
    rows = [row + [""] * (width - len(row)) for row in rows]
    lines = [
        "| " + " | ".join(rows[0]) + " |",
        "| " + " | ".join(["---"] * width) + " |",
    ]
    lines += ["| " + " | ".join(row) + " |" for row in rows[1:]]
    return "\n".join(lines)
