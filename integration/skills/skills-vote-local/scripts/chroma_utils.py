from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import Protocol

COLLECTION_DELETE_BATCH_SIZE = 1024
COLLECTION_UPSERT_BATCH_SIZE = 128
RECOVERABLE_COLLECTION_ERROR_SNIPPETS = (
    "Error sending backfill request to compactor",
    "Failed to apply logs to the hnsw segment writer",
)


class ChromaDocument(Protocol):
    skill_id: str

    def retrieval_text(self) -> str: ...

    def chroma_metadata(self) -> dict[str, str | int]: ...


EmbedTexts = Callable[[list[str], dict], list[list[float]]]


def _batched[T](items: list[T], batch_size: int) -> Iterator[list[T]]:
    for start in range(0, len(items), batch_size):
        yield items[start : start + batch_size]


def create_client(chroma_path: str):
    from chromadb import PersistentClient

    return PersistentClient(path=chroma_path)


def get_collection(client, config: dict):
    chroma_cfg = config["chroma"]
    return client.get_or_create_collection(
        name=chroma_cfg["collection"],
        metadata={"hnsw:space": "cosine"},
    )


def reset_collection(client, config: dict) -> None:
    collection_name = config["chroma"]["collection"]
    existing_names = _collection_names(client)
    if collection_name not in existing_names:
        return
    client.delete_collection(collection_name)


def _collection_names(client) -> set[str]:
    return {
        str(getattr(collection, "name", collection))
        for collection in client.list_collections()
    }


def upsert_documents(
    collection,
    documents: list[ChromaDocument],
    config: dict,
    *,
    embed_texts: EmbedTexts,
) -> None:
    if not documents:
        return

    for batch in _batched(documents, COLLECTION_UPSERT_BATCH_SIZE):
        retrieval_texts = [document.retrieval_text() for document in batch]
        embeddings = embed_texts(retrieval_texts, config)
        collection.upsert(
            ids=[document.skill_id for document in batch],
            documents=retrieval_texts,
            metadatas=[document.chroma_metadata() for document in batch],
            embeddings=embeddings,
        )


def load_collection_metadata_map(collection) -> dict[str, dict]:
    collection_count = int(collection.count())
    if collection_count < 1:
        return {}

    result = collection.get(limit=collection_count, include=["metadatas"])
    return {
        str(item_id): metadata
        for item_id, metadata in zip(
            result.get("ids") or [],
            result.get("metadatas") or [],
            strict=False,
        )
    }


def delete_documents(collection, document_ids: list[str]) -> None:
    if not document_ids:
        return

    for batch in _batched(document_ids, COLLECTION_DELETE_BATCH_SIZE):
        collection.delete(ids=batch)


def query_collection(
    rewritten_query: str,
    config: dict,
    query_top_k: int,
    *,
    embed_texts: EmbedTexts,
) -> dict:
    client = create_client(config["chroma"]["path"])
    collection = get_collection(client, config)
    query_embedding = embed_texts([rewritten_query], config)[0]
    return collection.query(
        query_embeddings=[query_embedding],
        n_results=query_top_k,
        include=["metadatas", "distances"],
    )


def is_recoverable_collection_error(exc: Exception) -> bool:
    message = str(exc)
    return any(snippet in message for snippet in RECOVERABLE_COLLECTION_ERROR_SNIPPETS)


def raise_collection_rebuild_required(exc: Exception) -> None:
    raise RuntimeError(
        "Collection state is unhealthy. Run `uv run scripts/index.py` to rebuild, then retry the query."
    ) from exc
