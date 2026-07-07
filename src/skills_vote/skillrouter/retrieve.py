from __future__ import annotations

from pathlib import Path

import faiss
import numpy as np


def query(
    query: np.ndarray,
    docs: np.ndarray,
    top_k: int = 50,
) -> tuple[np.ndarray, np.ndarray]:
    query_embeddings = np.asarray(query, dtype=np.float32)
    if query_embeddings.ndim == 1:
        query_embeddings = query_embeddings[None, :]
    query_embeddings = np.ascontiguousarray(query_embeddings)

    doc_embeddings = np.ascontiguousarray(np.asarray(docs, dtype=np.float32))
    index = faiss.IndexFlatIP(doc_embeddings.shape[1])
    index.add(doc_embeddings)
    return index.search(query_embeddings, min(top_k, len(doc_embeddings)))


def query_npy(
    query_npy_path: Path,
    docs_npy_path: Path,
    top_k: int = 50,
) -> tuple[np.ndarray, np.ndarray]:
    return query(
        np.load(query_npy_path),
        np.load(docs_npy_path),
        top_k=top_k,
    )
