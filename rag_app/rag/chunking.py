"""Split a document's Markdown into retrieval-sized, section-aware chunks.

Design:
- Headings are not chunks. They become the "section path" (e.g.
  "2. Remote Work & PTO Policy > 2.1 Paid Time Off") that is prefixed to every chunk
  under them, so a chunk is understandable on its own, for both search and the LLM.
- Text inside a section is split with LangChain's RecursiveCharacterTextSplitter,
  which prefers to break on paragraph, then line, then sentence boundaries and
  handles overlap. It also splits paragraphs that are longer than a chunk.
- Tables are never split mid-row. Large tables are split by rows and every part
  repeats the header row, so "Project Kestrel | Maya Lin-Sato" still carries the
  meaning "Code Name | Lead Engineer".
"""

import re

from langchain_core.documents import Document as Chunk
from langchain_text_splitters import RecursiveCharacterTextSplitter

HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$")
_TABLE_SEPARATOR_RE = re.compile(r"^\|\s*-{3,}")


def chunk_markdown(
    markdown: str,
    *,
    chunk_size: int = 800,
    chunk_overlap: int = 100,
    metadata: dict | None = None,
) -> list[Chunk]:
    """Split Markdown into chunks; `metadata` is copied onto every chunk."""
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=["\n\n", "\n", ". ", " ", ""],
    )
    base_metadata = metadata or {}
    chunks: list[Chunk] = []
    headings: list[tuple[int, str]] = []  # stack of (level, title)
    pending_text: list[str] = []

    def section() -> str:
        return " > ".join(title for _, title in headings)

    def add_chunk(body: str, is_table: bool) -> None:
        sec = section()
        content = f"Section: {sec}\n{body}" if sec else body
        chunks.append(
            Chunk(
                page_content=content,
                metadata={**base_metadata, "section": sec, "is_table": is_table},
            )
        )

    def flush_text() -> None:
        if pending_text:
            for piece in splitter.split_text("\n\n".join(pending_text)):
                add_chunk(piece, is_table=False)
            pending_text.clear()

    for block in (b.strip() for b in markdown.split("\n\n")):
        if not block:
            continue
        heading = HEADING_RE.match(block)
        if heading:
            flush_text()
            level = len(heading.group(1))
            while headings and headings[-1][0] >= level:
                headings.pop()
            headings.append((level, heading.group(2).strip()))
        elif is_markdown_table(block):
            flush_text()
            for part in split_table(block, chunk_size):
                add_chunk(part, is_table=True)
        else:
            pending_text.append(block)
    flush_text()
    return chunks


def is_markdown_table(block: str) -> bool:
    lines = block.splitlines()
    return (
        len(lines) >= 2
        and lines[0].lstrip().startswith("|")
        and bool(_TABLE_SEPARATOR_RE.match(lines[1].strip()))
    )


def split_table(table: str, max_chars: int) -> list[str]:
    """Split a Markdown table by rows, repeating the header in every part."""
    lines = [line for line in table.splitlines() if line.strip()]
    header, rows = lines[:2], lines[2:]
    if len(table) <= max_chars or not rows:
        return [table]

    parts: list[str] = []
    current: list[str] = []
    header_len = sum(len(line) + 1 for line in header)
    size = header_len
    for row in rows:
        if current and size + len(row) + 1 > max_chars:
            parts.append("\n".join(header + current))
            current, size = [], header_len
        current.append(row)
        size += len(row) + 1
    parts.append("\n".join(header + current))
    return parts
