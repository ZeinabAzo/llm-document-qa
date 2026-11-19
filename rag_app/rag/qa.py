"""Prompt + LLM call: turn a question and retrieved passages into a grounded answer."""

from langchain_core.language_models import BaseChatModel
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable

from .index import SearchResult

FALLBACK_ANSWER = "I don't have enough information in the provided documents to answer this question."

SYSTEM_PROMPT = f"""You answer questions using ONLY the numbered context passages provided.

Rules:
1. Use only facts stated in the passages. Never use outside knowledge, assumptions or guesses.
2. If the passages do not contain the answer, reply with exactly this sentence and nothing else:
{FALLBACK_ANSWER}
3. After each fact, cite the passage(s) it came from by number, like [1] or [2][3].
4. Be concise and direct. Answer in the same language as the question."""

HUMAN_PROMPT = """Context passages:

{context}

Question: {question}"""

PROMPT = ChatPromptTemplate.from_messages([("system", SYSTEM_PROMPT), ("human", HUMAN_PROMPT)])


def build_answer_chain(llm: BaseChatModel) -> Runnable:
    """LangChain Expression Language pipeline: prompt -> chat model -> plain string."""
    return PROMPT | llm | StrOutputParser()


def format_context(results: list[SearchResult]) -> str:
    """Number each passage and label it with its document so the LLM can cite it.

    The section is already the first line of each chunk's text, so it is not repeated.
    """
    passages = []
    for number, result in enumerate(results, start=1):
        title = result.chunk.metadata.get("document_title", "unknown document")
        passages.append(f"[{number}] Document: {title}\n{result.chunk.page_content}")
    return "\n\n---\n\n".join(passages)
