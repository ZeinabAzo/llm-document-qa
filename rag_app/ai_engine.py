import os
from dotenv import load_dotenv
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS
from langchain_openai import ChatOpenAI
from .models import Document

# Load OPENROUTER_API_KEY from .env
load_dotenv()

# Replace this with the exact model ID copied from OpenRouter
MODEL_NAME = "nvidia/nemotron-3-ultra-550b-a55b:free"


def get_retriever():
    """Build a FAISS retriever from all stored Document texts."""
    docs = Document.objects.exclude(extracted_text__isnull=True).exclude(extracted_text="")
    texts = [doc.extracted_text for doc in docs]

    if not texts:
        return None

    # Split long texts into overlapping chunks for better retrieval
    splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)
    chunks = splitter.create_documents(texts)

    # Lightweight CPU-friendly embedding model
    embeddings = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")
    vector_store = FAISS.from_documents(chunks, embeddings)

    return vector_store.as_retriever(search_kwargs={"k": 3})


def ask_question(question: str) -> str:
    """Retrieve relevant chunks and generate an answer via OpenRouter."""
    retriever = get_retriever()
    if not retriever:
        return "No documents found in the database. Please upload a .docx file first."

    # 1. Retrieve relevant context
    relevant_docs = retriever.invoke(question)
    context = "\n\n".join([doc.page_content for doc in relevant_docs])

    # 2. Connect to OpenRouter using the OpenAI-compatible client
    llm = ChatOpenAI(
        model=MODEL_NAME,
        openai_api_key=os.getenv("OPENROUTER_API_KEY"),
        openai_api_base="https://openrouter.ai/api/v1",
        temperature=0.2, # avoid hallucination
    )

    # 3. Build prompt and get answer
    prompt = (
        "Answer the question based ONLY on the following context. "
        "If the answer is not in the context, say you don't know.\n\n"
        f"Context:\n{context}\n\n"
        f"Question: {question}"
    )

    response = llm.invoke(prompt)
    return response.content