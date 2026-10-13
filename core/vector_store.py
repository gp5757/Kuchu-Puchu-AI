import os 
import functools
import torch
from dotenv import load_dotenv

load_dotenv()

# Set HF_TOKEN if available to avoid unauthenticated download throttling
hf_key = os.getenv("HUGGINGFACE_API_KEY")
if hf_key and "HF_TOKEN" not in os.environ:
    os.environ["HF_TOKEN"] = hf_key

from langchain_chroma import Chroma 
try:
    from langchain_huggingface import HuggingFaceEmbeddings
except ImportError:
    from langchain_community.embeddings import HuggingFaceEmbeddings

from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document

CHROMA_DIR = os.getenv("CHROMA_PERSIST_DIR", "vector_db")
os.makedirs(CHROMA_DIR, exist_ok=True)
COLLECTION_NAME = "meeting_transcript"
EMBEDDING_MODEL = "all-MiniLM-L6-v2"

_embeddings_instance = None
_chroma_client_instance = None
_cached_vector_store = None


class CachedHuggingFaceEmbeddings(HuggingFaceEmbeddings):
    """
    Subclass that adds an in-memory LRU cache for query embeddings.
    Avoids redundant PyTorch forward passes on CPU for identical or repeated questions.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._cache = {}

    def embed_query(self, text: str):
        cleaned = text.strip()
        if cleaned in self._cache:
            return self._cache[cleaned]
        # Keep cache bounded to prevent memory growth
        if len(self._cache) > 256:
            self._cache.pop(next(iter(self._cache)))
        result = super().embed_query(text)
        self._cache[cleaned] = result
        return result


def get_chroma_client():
    """Singleton persistent Chroma client for fast index reuse."""
    global _chroma_client_instance
    if _chroma_client_instance is None:
        import chromadb
        _chroma_client_instance = chromadb.PersistentClient(path=CHROMA_DIR)
    return _chroma_client_instance


def get_embeddings():
    """Initializes and returns cached singleton HuggingFace embeddings."""
    global _embeddings_instance
    if _embeddings_instance is None:
        device = "cuda" if torch.cuda.is_available() else "cpu"
        _embeddings_instance = CachedHuggingFaceEmbeddings(
            model_name=EMBEDDING_MODEL,
            model_kwargs={"device": device},
            encode_kwargs={"batch_size": 32, "normalize_embeddings": True}
        )
    return _embeddings_instance


def warmup_embeddings():
    """Helper to warm up the embedding model on server startup in background."""
    try:
        emb = get_embeddings()
        emb.embed_query("warmup")
    except Exception as e:
        print(f"[vector_store] Warmup notice: {e}")


def build_vector_store(transcript: str) -> Chroma:
    global _cached_vector_store
    print("[vector_store] Building vector store...")

    clean_text = (transcript or "").strip()
    if not clean_text:
        clean_text = "No spoken content detected in this recording."

    # Optimal semantic chunks: 750 chars (~110 words) provides complete thoughts,
    # cuts number of embedding calls in half, and significantly improves RAG accuracy.
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=750,
        chunk_overlap=75
    )

    chunks = splitter.split_text(clean_text)
    if not chunks:
        chunks = [clean_text]

    docs = [
        Document(page_content=chunk, metadata={'chunk_index': i})
        for i, chunk in enumerate(chunks)
    ]

    embeddings = get_embeddings()
    try:
        client = get_chroma_client()
        try:
            client.delete_collection(COLLECTION_NAME)
        except Exception:
            pass
        vector_store = Chroma(
            client=client,
            collection_name=COLLECTION_NAME,
            embedding_function=embeddings
        )
        vector_store.add_documents(docs)
    except Exception as e:
        print(f"[vector_store] Persistent store notice: {e}. Using direct Chroma...")
        vector_store = Chroma.from_documents(
            documents=docs,
            embedding=embeddings
        )

    _cached_vector_store = vector_store
    print(f"[vector_store] Vector store indexed with {len(docs)} semantic chunks.")
    return vector_store


def load_vector_store() -> Chroma:
    global _cached_vector_store
    if _cached_vector_store is not None:
        return _cached_vector_store

    embeddings = get_embeddings()
    try:
        client = get_chroma_client()
        vector_store = Chroma(
            client=client,
            collection_name=COLLECTION_NAME,
            embedding_function=embeddings
        )
    except Exception:
        vector_store = Chroma(
            collection_name=COLLECTION_NAME,
            embedding_function=embeddings,
            persist_directory=CHROMA_DIR
        )
    _cached_vector_store = vector_store
    return vector_store


def get_retriever(vector_store: Chroma, k: int = 3):
    """
    Returns an optimized retriever with k=3 to minimize token context size and LLM latency
    while providing complete context.
    """
    return vector_store.as_retriever(
        search_type='similarity',
        search_kwargs={"k": k}
    )