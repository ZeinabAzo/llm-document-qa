"""Test helpers: build .docx files in memory and fake the expensive/external parts."""

import io
from contextlib import ExitStack
from unittest import mock

import docx
from django.core.files.uploadedfile import SimpleUploadedFile
from langchain_core.embeddings import DeterministicFakeEmbedding
from langchain_core.language_models import FakeListChatModel

from rag_app import services
from rag_app.rag.qa import build_answer_chain


def make_docx(build) -> bytes:
    """Create a .docx in memory; `build(document)` adds the content."""
    document = docx.Document()
    build(document)
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def bold_paragraph(document, text: str) -> None:
    document.add_paragraph().add_run(text).bold = True


def handbook_docx(extra: str = "") -> bytes:
    """A small document with the same quirks as the real sample handbook."""

    def build(d):
        bold_paragraph(d, "1. Leave Policy")  # "fake" heading: bold Normal paragraph
        bold_paragraph(d, "1.1 Vacation")
        d.add_paragraph("Employees receive 22 days of paid time off per year.")
        d.add_heading("2. Security", level=1)  # real Word heading style
        d.add_paragraph("Report lost laptops to security-sos@example.com within 2 hours.")
        d.add_paragraph("Use a passphrase of 16 characters.", style="List Bullet")
        if extra:
            d.add_paragraph(extra)

    return make_docx(build)


def upload(name: str, content: bytes) -> SimpleUploadedFile:
    return SimpleUploadedFile(
        name,
        content,
        content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )


def fake_rag(answers: list[str] | None = None, llm_error: Exception | None = None) -> ExitStack:
    """Replace the embedding model and the LLM with deterministic offline fakes."""
    stack = ExitStack()
    stack.enter_context(
        mock.patch.object(
            services, "_load_embeddings", return_value=DeterministicFakeEmbedding(size=16)
        )
    )
    if llm_error is not None:
        chain = mock.Mock()
        chain.invoke.side_effect = llm_error
    else:
        chain = build_answer_chain(FakeListChatModel(responses=answers or ["22 days [1]."]))
    stack.enter_context(mock.patch.object(services, "get_answer_chain", return_value=chain))
    services.document_index.reset()
    stack.callback(services.document_index.reset)
    return stack
