import os
import sys
import asyncio

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
if hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from dotenv import load_dotenv

load_dotenv()
from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough, RunnableLambda
from core.vector_store import build_vector_store, load_vector_store, get_retriever

_llm_instance = None


def get_llm():
    """Returns a singleton, optimized ChatGroq client with resilient fallback and timeouts."""
    global _llm_instance
    if _llm_instance is None:
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise ValueError("GROQ_API_KEY environment variable is missing. Please set it in your Railway/Render environment.")

        # Request timeout and max_tokens prevent hanging and runaway response latency
        primary_llm = ChatGroq(
            model="openai/gpt-oss-120b",
            api_key=api_key,
            temperature=0.2,
            request_timeout=15,
            max_tokens=600,
        )
        fallback_llm = ChatGroq(
            model="openai/gpt-oss-20b",
            api_key=api_key,
            temperature=0.2,
            request_timeout=15,
            max_tokens=600,
        )
        _llm_instance = primary_llm.with_fallbacks([fallback_llm])
    return _llm_instance


def format_docs(docs):
    """Formats and deduplicates retrieved context documents to reduce context tokens."""
    seen = set()
    unique_chunks = []
    for doc in docs:
        content = (doc.page_content if hasattr(doc, "page_content") else str(doc)).strip()
        if content and content not in seen:
            seen.add(content)
            unique_chunks.append(content)
    return "\n\n".join(unique_chunks) if unique_chunks else "No specific transcript context found."


def create_rag_chain_from_vector_store(vector_store):
    retriever = get_retriever(vector_store, k=3)
    llm = get_llm()
    prompt = ChatPromptTemplate.from_messages([
        (
            "system",
            """You are an expert meeting assistant. Answer the user's question 
based ONLY on the meeting transcript context provided below.

If the answer is not found in the context, say: 
"I could not find this information in the meeting transcript."

Always be concise and precise. If quoting someone, mention it clearly.

Context from meeting transcript:
{context}""",
        ),
        ("human", "{question}"),
    ])
    return (
        {"context": retriever | RunnableLambda(format_docs), "question": RunnablePassthrough()}
        | prompt
        | llm
        | StrOutputParser()
    )


def build_rag_chain(transcript: str):
    vector_store = build_vector_store(transcript)
    return create_rag_chain_from_vector_store(vector_store)


def load_rag_chain():
    vector_store = load_vector_store()
    return create_rag_chain_from_vector_store(vector_store)


async def ask_question_async(rag_chain, question: str) -> str:
    """
    Asynchronously queries the RAG chain without blocking the FastAPI event loop.
    Uses native ainvoke when available, falling back to a threadpool worker.
    """
    clean_q = question.strip() if question else ""
    if not clean_q:
        return "Please ask a specific question regarding the lecture or meeting."

    try:
        safe_q = clean_q.encode("ascii", errors="backslashreplace").decode("ascii")
        print(f"[RAG] Question: {safe_q}")
    except Exception:
        pass

    if hasattr(rag_chain, "ainvoke"):
        answer = await rag_chain.ainvoke(clean_q)
    else:
        answer = await asyncio.to_thread(rag_chain.invoke, clean_q)

    if not isinstance(answer, str):
        answer = str(answer)

    try:
        safe_a = answer.encode("ascii", errors="backslashreplace").decode("ascii")
        print(f"[RAG] Answer: {safe_a}")
    except Exception:
        pass

    return answer.strip()


def ask_question(rag_chain, question: str) -> str:
    """Synchronous wrapper for ask_question backwards compatibility."""
    clean_q = question.strip() if question else ""
    if not clean_q:
        return "Please ask a specific question regarding the lecture or meeting."

    answer = rag_chain.invoke(clean_q)
    if not isinstance(answer, str):
        answer = str(answer)
    return answer.strip()