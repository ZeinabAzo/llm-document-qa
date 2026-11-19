"""Business logic shared by the REST API, the admin and management commands.

Views and admin classes stay thin: they validate input, call a function here, and
turn the result (or exception) into an HTTP response / form error.
"""

import hashlib
import logging
import threading
import time
from dataclasses import dataclass
from functools import lru_cache

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import UploadedFile
from django.db.models import Count, Max
from langchain_core.embeddings import Embeddings
from langchain_core.language_models import BaseChatModel
from langchain_core.runnables import Runnable

from .models import Document, QAHistory
from .rag.chunking import chunk_markdown
from .rag.extract import docx_to_markdown
from .rag.index import HybridIndex
from .rag.qa import build_answer_chain, format_context

logger = logging.getLogger(__name__)


# --- Errors ---------------------------------------------------------------------


class QAError(Exception):
    """A question could not be answered. The message is safe to show to users."""


class NoDocumentsError(QAError):
    pass


class LLMError(QAError):
    pass


# --- Documents ------------------------------------------------------------------


@dataclass(frozen=True)
class ParsedUpload:
    text: str
    content_hash: str


def parse_docx_upload(file: UploadedFile, *, exclude_pk: int | None = None) -> ParsedUpload:
    """Validate an uploaded .docx and extract its text, before anything is saved.

    Raises `ValidationError` (shown as a form/serializer error) if the file is too
    large, a duplicate of an existing document, unreadable, or has no text.
    """
    max_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
    if file.size > max_bytes:
        raise ValidationError(f"File is larger than {settings.MAX_UPLOAD_SIZE_MB} MB.")

    try:
        file.seek(0)
        text = docx_to_markdown(file)
    except Exception as exc:  # python-docx raises several unrelated exception types
        logger.warning("Could not read %s: %s", file.name, exc)
        raise ValidationError("Could not read this file. Is it a valid .docx document?") from exc
    finally:
        file.seek(0)  # the storage backend reads the file again when saving

    if not text.strip():
        raise ValidationError("The document contains no text.")

    # Hash the extracted *text*, not the file bytes: Word stores timestamps inside
    # the .docx, so re-saving the same document changes its bytes but not its text.
    content_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
    duplicate = Document.objects.filter(content_hash=content_hash).exclude(pk=exclude_pk).first()
    if duplicate:
        raise ValidationError(
            f'This document was already uploaded as "{duplicate.title}" (id {duplicate.pk}).'
        )
    return ParsedUpload(text=text, content_hash=content_hash)


def apply_parsed_upload(document: Document, parsed: ParsedUpload) -> None:
    document.extracted_text = parsed.text
    document.content_hash = parsed.content_hash


# --- Search index ----------------------------------------------------------------


def _load_embeddings() -> Embeddings:
    # Imported lazily: sentence-transformers pulls in PyTorch, which would add
    # seconds to every `manage.py` command that never needs embeddings.
    from langchain_huggingface import HuggingFaceEmbeddings

    return HuggingFaceEmbeddings(model_name=settings.EMBEDDING_MODEL)


def build_chunks(documents) -> list:
    chunks = []
    for doc in documents:
        chunks += chunk_markdown(
            doc.extracted_text,
            chunk_size=settings.CHUNK_SIZE,
            chunk_overlap=settings.CHUNK_OVERLAP,
            metadata={"document_id": doc.pk, "document_title": doc.title},
        )
    return chunks


class DocumentIndex:
    """Keeps one in-memory HybridIndex in sync with the Document table.

    Before each search we run one cheap aggregate query (row count + latest
    `updated_at`). If it differs from the last build, documents were added, edited
    or deleted, and the index is rebuilt. A lock makes sure concurrent requests
    don't rebuild it twice.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._embeddings: Embeddings | None = None
        self._index: HybridIndex | None = None
        self._signature: tuple | None = None

    def get(self) -> HybridIndex | None:
        """Return an up-to-date index, or None if there are no documents."""
        stats = Document.objects.aggregate(count=Count("id"), latest=Max("updated_at"))
        signature = (stats["count"], stats["latest"])
        with self._lock:
            if signature != self._signature:
                self._index = self._build() if stats["count"] else None
                self._signature = signature
            return self._index

    def _build(self) -> HybridIndex | None:
        started = time.perf_counter()
        if self._embeddings is None:
            self._embeddings = _load_embeddings()
        chunks = build_chunks(Document.objects.only("id", "title", "extracted_text"))
        index = HybridIndex(chunks, self._embeddings) if chunks else None
        logger.info("Built index: %d chunks in %.1fs", len(chunks), time.perf_counter() - started)
        return index

    def reset(self) -> None:
        with self._lock:
            self._index = self._signature = None


document_index = DocumentIndex()


# --- Question answering -------------------------------------------------------------


@lru_cache(maxsize=1)
def get_llm() -> BaseChatModel:
    """Create the chat model once and reuse its HTTP connection pool."""
    if not settings.OPENROUTER_API_KEY:
        raise LLMError("The LLM is not configured: set OPENROUTER_API_KEY.")
    from langchain_openai import ChatOpenAI

    # OpenRouter exposes an OpenAI-compatible API, so the OpenAI client works as-is.
    return ChatOpenAI(
        model=settings.OPENROUTER_MODEL,
        api_key=settings.OPENROUTER_API_KEY,
        base_url=settings.OPENROUTER_BASE_URL,
        temperature=settings.LLM_TEMPERATURE,
        timeout=settings.LLM_TIMEOUT_SECONDS,
        max_retries=2,
    )


@lru_cache(maxsize=1)
def get_answer_chain() -> Runnable:
    return build_answer_chain(get_llm())


@dataclass(frozen=True)
class Answer:
    text: str
    sources: list[dict]
    model_name: str
    latency_ms: int


def answer_question(question: str, top_k: int | None = None) -> Answer:
    """Retrieve relevant passages and ask the LLM to answer from them only."""
    started = time.perf_counter()
    index = document_index.get()
    if index is None:
        raise NoDocumentsError("No documents have been uploaded yet.")

    results = index.search(question, k=top_k or settings.RETRIEVAL_TOP_K)
    retrieved_at = time.perf_counter()

    try:
        text = get_answer_chain().invoke(
            {"context": format_context(results), "question": question}
        )
    except QAError:
        raise
    except Exception as exc:  # network errors, timeouts, rate limits, bad responses
        logger.exception("LLM call failed")
        raise LLMError("The language model is unavailable right now. Please try again.") from exc

    finished = time.perf_counter()
    logger.info(
        "Answered question: retrieval %.0f ms, LLM %.0f ms",
        (retrieved_at - started) * 1000,
        (finished - retrieved_at) * 1000,
    )
    sources = [
        {
            "number": number,
            "document_id": r.chunk.metadata["document_id"],
            "document_title": r.chunk.metadata["document_title"],
            "section": r.chunk.metadata["section"],
            "excerpt": r.chunk.page_content,
            "score": round(r.score, 4),
            "vector_rank": r.vector_rank,
            "keyword_rank": r.keyword_rank,
        }
        for number, r in enumerate(results, start=1)
    ]
    return Answer(
        text=text.strip(),
        sources=sources,
        model_name=settings.OPENROUTER_MODEL,
        latency_ms=round((finished - started) * 1000),
    )


def apply_answer(entry: QAHistory, answer: Answer) -> None:
    entry.answer = answer.text
    entry.sources = answer.sources
    entry.model_name = answer.model_name
    entry.latency_ms = answer.latency_ms


def ask(question: str, top_k: int | None = None) -> QAHistory:
    """Answer a question and store it in the Q&A history."""
    answer = answer_question(question, top_k)
    entry = QAHistory(question=question)
    apply_answer(entry, answer)
    entry.save()
    return entry
