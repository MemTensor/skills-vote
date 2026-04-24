from __future__ import annotations

import fnmatch
import glob
import hashlib
import json
import math
import os
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

import yaml
from chroma_utils import (
    create_client,
    delete_documents,
    get_collection,
    is_recoverable_collection_error,
    load_collection_metadata_map,
    query_collection,
    raise_collection_rebuild_required,
    reset_collection,
    upsert_documents,
)

TOKEN_RE = re.compile(r"[a-zA-Z0-9_./+-]+")
RETRIEVAL_TEXT_VERSION = "title-description-v1"
SKILL_FILE_NAME = "SKILL.md"
DEFAULT_CHROMA_PATH = "../output/chroma/skills_vote_local"
DEFAULT_COLLECTION_NAME = "skills_vote_local"
DEFAULT_EMBEDDING_PROVIDER = "openai-compatible"
DEFAULT_EMBEDDING_MODEL = "bge-m3"
DEFAULT_EMBEDDING_DIMENSIONS = 1024
DEFAULT_EMBEDDING_API_KEY_ENV = "OPENAI_API_KEY"
DEFAULT_EMBEDDING_BASE_URL = "https://api.openai.com/v1"
DEFAULT_TOP_K = 5
DEFAULT_INCLUDE_PATTERNS = ("**/SKILL.md",)
DEFAULT_EXCLUDE_PATTERNS = (
    "**/.git/**",
    "**/.venv/**",
    "**/node_modules/**",
    "**/__pycache__/**",
)
CURRENT_SKILL_ROOT = Path(__file__).resolve().parent.parent


@dataclass(slots=True)
class SkillDocument:
    skill_id: str
    title: str
    description: str
    path: str
    content_hash: str
    content_mtime_ns: int
    content_size_bytes: int

    def retrieval_text(self) -> str:
        return f"Title: {self.title}\nDescription: {self.description}"

    def chroma_metadata(self) -> dict[str, str | int]:
        return {
            "skill_id": self.skill_id,
            "title": self.title,
            "description": self.description,
            "path": self.path,
            "content_hash": self.content_hash,
            "content_mtime_ns": self.content_mtime_ns,
            "content_size_bytes": self.content_size_bytes,
            "retrieval_text_version": RETRIEVAL_TEXT_VERSION,
        }


@dataclass(slots=True)
class RecommendCandidate:
    skill_name: str
    path: str
    description: str
    score: float

    @classmethod
    def from_query_result(cls, metadata: dict, distance: object) -> RecommendCandidate:
        title = str(
            metadata.get("title") or metadata.get("skill_name") or "unknown-skill"
        )
        return cls(
            skill_name=title,
            path=str(metadata.get("path") or ""),
            description=str(metadata.get("description") or ""),
            score=_score_from_distance(distance),
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "skill_name": self.skill_name,
            "path": self.path,
            "description": self.description,
            "score": round(self.score, 4),
        }


def load_config(config_path: str | Path) -> dict:
    config_path = Path(config_path).resolve()
    config = _read_config_yaml(config_path)
    _apply_config_defaults(config)
    _normalize_config(config, config_path.parent)
    _validate_config(config)
    return config


def _read_config_yaml(config_path: Path) -> dict:
    config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    if not isinstance(config, dict):
        raise ValueError("Config root must be a YAML object")
    return config


def _apply_config_defaults(config: dict) -> None:
    skill_library = config.setdefault("skill_library", {})
    chroma = config.setdefault("chroma", {})
    embedding = config.setdefault("embedding", {})
    retrieval = config.setdefault("retrieval", {})
    config.setdefault("indexing", {})

    skill_library.setdefault("roots", [])
    skill_library.setdefault("include", list(DEFAULT_INCLUDE_PATTERNS))
    skill_library.setdefault("exclude", list(DEFAULT_EXCLUDE_PATTERNS))
    skill_library.setdefault("extend_include", [])
    skill_library.setdefault("extend_exclude", [])

    chroma.setdefault("path", DEFAULT_CHROMA_PATH)
    chroma.setdefault("collection", DEFAULT_COLLECTION_NAME)

    embedding.setdefault("provider", DEFAULT_EMBEDDING_PROVIDER)
    embedding.setdefault("model", DEFAULT_EMBEDDING_MODEL)
    embedding.setdefault("dimensions", DEFAULT_EMBEDDING_DIMENSIONS)
    embedding.setdefault("api_key_env", DEFAULT_EMBEDDING_API_KEY_ENV)
    embedding.setdefault("api_key", "")
    embedding.setdefault("base_url", DEFAULT_EMBEDDING_BASE_URL)
    embedding.setdefault("extra_headers", {})

    retrieval.setdefault("top_k", DEFAULT_TOP_K)
    retrieval.setdefault("final_k", DEFAULT_TOP_K)


def _normalize_config(config: dict, base_dir: Path) -> None:
    skill_library = config["skill_library"]
    chroma = config["chroma"]
    indexing = config["indexing"]

    auto_update = indexing.get("update_on_start")
    if auto_update is None:
        auto_update = indexing.get("rebuild_on_start", True)
    indexing["update_on_start"] = bool(auto_update)

    skill_library["_scan_include_patterns"] = _build_scan_include_patterns(
        base_dir,
        skill_library,
    )
    chroma["path"] = str(_resolve(base_dir, chroma["path"]))


def _resolve(base_dir: Path, raw_path: str) -> Path:
    path = Path(raw_path)
    if path.is_absolute():
        return path.resolve()
    return (base_dir / path).resolve()


def _validate_config(config: dict) -> None:
    skill_library = config["skill_library"]
    include_patterns = [
        str(pattern).strip()
        for pattern in skill_library.get("_scan_include_patterns", [])
        if str(pattern).strip()
    ]
    if not include_patterns:
        raise ValueError(
            "skill_library.include must contain at least one real glob pattern"
        )
    if any("/absolute/path/to/" in pattern for pattern in include_patterns):
        raise ValueError(
            "Replace placeholder paths in skill_library.include with real skill globs"
        )

    retrieval = config["retrieval"]
    _require_positive_int(retrieval.get("top_k", DEFAULT_TOP_K), "retrieval.top_k")

    embedding = config["embedding"]
    provider = embedding.get("provider", DEFAULT_EMBEDDING_PROVIDER)
    if provider == "hashing":
        _require_positive_int(
            embedding.get("dimensions", DEFAULT_EMBEDDING_DIMENSIONS),
            "embedding.dimensions",
        )
    elif (
        provider == "openai-compatible"
        and not str(embedding.get("model") or "").strip()
    ):
        raise ValueError(
            "embedding.model is required when embedding.provider is openai-compatible"
        )


def _require_positive_int(value: object, label: str) -> int:
    try:
        numeric_value = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be a positive integer") from exc
    if numeric_value < 1:
        raise ValueError(f"{label} must be a positive integer")
    return numeric_value


def parse_frontmatter(raw_text: str) -> tuple[dict, str]:
    stripped = raw_text.lstrip()
    lines = stripped.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        return {}, raw_text

    end_index = next(
        (
            index
            for index, line in enumerate(lines[1:], start=1)
            if line.strip() == "---"
        ),
        None,
    )
    if end_index is None:
        return {}, raw_text

    try:
        frontmatter = yaml.safe_load("".join(lines[1:end_index])) or {}
    except yaml.YAMLError:
        frontmatter = {}

    body = "".join(lines[end_index + 1 :]).lstrip("\r\n")
    return frontmatter if isinstance(frontmatter, dict) else {}, body


def _extract_description(frontmatter: dict, body: str) -> str:
    description = str(frontmatter.get("description") or "").strip().strip("\"'")
    if description:
        return description

    for line in body.splitlines():
        text = line.strip()
        if text and not text.startswith("#"):
            return text[:240]
    return "No description provided."


def _matches_any(path_text: str, patterns: list[str]) -> bool:
    return any(fnmatch.fnmatch(path_text, pattern) for pattern in patterns)


def _collect_patterns(values: list[str] | tuple[str, ...] | None) -> list[str]:
    if not values:
        return []
    return [str(value).strip() for value in values if str(value).strip()]


def _is_absolute_pattern(raw_pattern: str) -> bool:
    return Path(os.path.expanduser(raw_pattern)).is_absolute()


def _normalize_scan_pattern(base_dir: Path, raw_pattern: str) -> str:
    expanded = os.path.expanduser(str(raw_pattern).strip())
    if Path(expanded).is_absolute():
        return os.path.normpath(expanded)
    return os.path.normpath(str(base_dir / expanded))


def _build_scan_include_patterns(base_dir: Path, skill_library: dict) -> list[str]:
    include_patterns = _collect_patterns(skill_library.get("include"))
    extend_include_patterns = _collect_patterns(skill_library.get("extend_include"))
    legacy_roots = [
        _resolve(base_dir, root)
        for root in _collect_patterns(skill_library.get("roots"))
    ]

    def resolve_patterns(patterns: list[str]) -> list[str]:
        if not legacy_roots:
            return [_normalize_scan_pattern(base_dir, pattern) for pattern in patterns]

        resolved_patterns: list[str] = []
        for pattern in patterns:
            if _is_absolute_pattern(pattern):
                resolved_patterns.append(_normalize_scan_pattern(base_dir, pattern))
                continue
            for root in legacy_roots:
                resolved_patterns.append(os.path.normpath(str(root / pattern)))
        return resolved_patterns

    return resolve_patterns(include_patterns) + resolve_patterns(
        extend_include_patterns
    )


def _should_scan_path(skill_path: Path, skill_library: dict) -> bool:
    excludes = list(skill_library.get("exclude", [])) + list(
        skill_library.get("extend_exclude", [])
    )
    return not (excludes and _matches_any(skill_path.as_posix(), excludes))


def _is_current_skill(skill_path: Path) -> bool:
    return skill_path.resolve().is_relative_to(CURRENT_SKILL_ROOT)


def _build_skill_id(skill_root: Path) -> str:
    return f"local:path:{hashlib.sha256(str(skill_root).encode('utf-8')).hexdigest()}"


def _is_scannable_skill_path(
    skill_path: Path,
    skill_library: dict,
    seen_paths: set[Path],
) -> bool:
    if skill_path.name != SKILL_FILE_NAME:
        return False
    if not skill_path.is_file():
        return False
    if skill_path in seen_paths:
        return False
    if _is_current_skill(skill_path):
        return False
    return _should_scan_path(skill_path, skill_library)


def _build_skill_document_from_bytes(
    skill_path: Path,
    raw_bytes: bytes,
    stat_result: os.stat_result,
) -> SkillDocument:
    raw = raw_bytes.decode("utf-8")
    frontmatter, body = parse_frontmatter(raw)
    skill_root = skill_path.parent.resolve()
    title = str(frontmatter.get("name") or skill_root.name).strip() or skill_root.name

    return SkillDocument(
        skill_id=_build_skill_id(skill_root),
        title=title,
        description=_extract_description(frontmatter, body),
        path=str(skill_path.resolve()),
        content_hash=hashlib.sha256(raw_bytes).hexdigest(),
        content_mtime_ns=stat_result.st_mtime_ns,
        content_size_bytes=stat_result.st_size,
    )


def build_skill_document(
    skill_path: Path,
    *,
    stat_result: os.stat_result | None = None,
) -> SkillDocument:
    current_stat = stat_result or skill_path.stat()
    raw_bytes = skill_path.read_bytes()
    return _build_skill_document_from_bytes(skill_path, raw_bytes, current_stat)


def _coerce_int(value: object) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _build_skill_document_from_metadata(
    skill_path: Path,
    *,
    stat_result: os.stat_result,
    metadata: dict,
) -> SkillDocument:
    skill_root = skill_path.parent.resolve()
    title = str(metadata.get("title") or metadata.get("skill_name") or skill_root.name)
    description = str(metadata.get("description") or "No description provided.")
    stored_size = _coerce_int(metadata.get("content_size_bytes"))
    return SkillDocument(
        skill_id=str(metadata.get("skill_id") or _build_skill_id(skill_root)),
        title=title.strip() or skill_root.name,
        description=description,
        path=str(skill_path.resolve()),
        content_hash=str(metadata.get("content_hash") or ""),
        content_mtime_ns=stat_result.st_mtime_ns,
        content_size_bytes=stored_size
        if stored_size is not None
        else stat_result.st_size,
    )


def _can_reuse_cached_document(
    stat_result: os.stat_result,
    metadata: dict | None,
) -> bool:
    if not metadata:
        return False
    if metadata.get("retrieval_text_version") != RETRIEVAL_TEXT_VERSION:
        return False
    if not metadata.get("content_hash"):
        return False
    stored_mtime = _coerce_int(metadata.get("content_mtime_ns"))
    if stored_mtime != stat_result.st_mtime_ns:
        return False
    stored_size = _coerce_int(metadata.get("content_size_bytes"))
    return stored_size is None or stored_size == stat_result.st_size


def _materialize_one_skill_document(
    skill_path: Path,
    metadata_index: dict[str, dict],
) -> SkillDocument | None:
    try:
        stat_result = skill_path.stat()
    except OSError:
        return None

    skill_id = _build_skill_id(skill_path.parent.resolve())
    metadata = metadata_index.get(skill_id)
    if _can_reuse_cached_document(stat_result, metadata):
        return _build_skill_document_from_metadata(
            skill_path,
            stat_result=stat_result,
            metadata=metadata or {},
        )

    try:
        return build_skill_document(skill_path, stat_result=stat_result)
    except (OSError, UnicodeError):
        return None


def discover_skill_paths(config: dict) -> list[Path]:
    skill_library = config["skill_library"]
    skill_paths: list[Path] = []
    seen_paths: set[Path] = set()
    include_patterns = skill_library.get("_scan_include_patterns", [])

    for include_pattern in include_patterns:
        for matched_path in glob.iglob(include_pattern, recursive=True):
            resolved_skill_path = Path(matched_path).resolve()
            if not _is_scannable_skill_path(
                resolved_skill_path,
                skill_library,
                seen_paths,
            ):
                continue

            seen_paths.add(resolved_skill_path)
            skill_paths.append(resolved_skill_path)

    return sorted(skill_paths)


def materialize_skill_documents(
    skill_paths: list[Path],
    *,
    metadata_by_id: dict[str, dict] | None = None,
) -> list[SkillDocument]:
    documents: list[SkillDocument] = []
    metadata_index = metadata_by_id or {}

    for skill_path in skill_paths:
        document = _materialize_one_skill_document(skill_path, metadata_index)
        if document is not None:
            documents.append(document)
    return documents


def tokenize(text: str) -> list[str]:
    return [token.lower() for token in TOKEN_RE.findall(text)]


def hash_embed(text: str, dimensions: int) -> list[float]:
    vector = [0.0] * dimensions
    for token in tokenize(text):
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        bucket = int.from_bytes(digest[:4], "big") % dimensions
        sign = 1.0 if digest[4] % 2 == 0 else -1.0
        vector[bucket] += sign

    norm = math.sqrt(sum(value * value for value in vector)) or 1.0
    return [value / norm for value in vector]


def _resolve_embedding_api_key(embedding_cfg: dict) -> str:
    api_key = str(embedding_cfg.get("api_key") or "").strip()
    if api_key:
        return api_key

    api_key_env = str(embedding_cfg.get("api_key_env", DEFAULT_EMBEDDING_API_KEY_ENV))
    api_key = os.getenv(api_key_env) or ""
    if api_key:
        return api_key

    raise RuntimeError(
        f"Missing embedding API key. Set embedding.api_key or env var: {api_key_env}"
    )


def _build_embedding_request(
    texts: list[str],
    embedding_cfg: dict,
) -> urllib.request.Request:
    api_key = _resolve_embedding_api_key(embedding_cfg)
    base_url = str(embedding_cfg.get("base_url", DEFAULT_EMBEDDING_BASE_URL)).rstrip(
        "/"
    )
    payload = json.dumps({"model": embedding_cfg["model"], "input": texts}).encode(
        "utf-8"
    )
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
        **dict(embedding_cfg.get("extra_headers", {})),
    }
    return urllib.request.Request(
        f"{base_url}/embeddings",
        data=payload,
        headers=headers,
        method="POST",
    )


def _parse_embedding_response(parsed: dict) -> list[list[float]]:
    data = parsed.get("data")
    if not isinstance(data, list):
        raise RuntimeError("Embedding API returned invalid payload")

    return [
        list(item["embedding"])
        for item in sorted(data, key=lambda item: item.get("index", 0))
    ]


def openai_compatible_embed(texts: list[str], embedding_cfg: dict) -> list[list[float]]:
    request = _build_embedding_request(texts, embedding_cfg)
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            parsed = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"Embedding API request failed: {exc.code} {body}") from exc

    return _parse_embedding_response(parsed)


def embed_texts(texts: list[str], config: dict) -> list[list[float]]:
    embedding_cfg = config["embedding"]
    provider = embedding_cfg.get("provider", DEFAULT_EMBEDDING_PROVIDER)
    if provider == "hashing":
        dimensions = int(embedding_cfg.get("dimensions", DEFAULT_EMBEDDING_DIMENSIONS))
        return [hash_embed(text, dimensions) for text in texts]
    if provider == "openai-compatible":
        return openai_compatible_embed(texts, embedding_cfg)
    raise ValueError(f"Unsupported embedding provider: {provider}")


def _build_index_result(
    *,
    mode: str,
    config: dict,
    scanned_documents: list[SkillDocument],
    indexed_documents: list[SkillDocument],
    unchanged_count: int | None = None,
    deleted_count: int | None = None,
) -> dict[str, object]:
    result: dict[str, object] = {
        "mode": mode,
        "skills_scanned": len(scanned_documents),
        "skills_indexed": len(indexed_documents),
        "collection": config["chroma"]["collection"],
        "chroma_path": config["chroma"]["path"],
        "skills": [document.title for document in indexed_documents],
    }
    if unchanged_count is not None:
        result["skills_unchanged"] = unchanged_count
    if deleted_count is not None:
        result["skills_deleted"] = deleted_count
    return result


def index_build(config: dict) -> dict[str, object]:
    skill_paths = discover_skill_paths(config)
    documents = materialize_skill_documents(skill_paths)
    client = create_client(config["chroma"]["path"])
    reset_collection(client, config)
    collection = get_collection(client, config)
    upsert_documents(collection, documents, config, embed_texts=embed_texts)
    return _build_index_result(
        mode="build",
        config=config,
        scanned_documents=documents,
        indexed_documents=documents,
    )


def _needs_reindex(document: SkillDocument, metadata: dict | None) -> bool:
    if not metadata:
        return True
    return (
        metadata.get("content_hash") != document.content_hash
        or metadata.get("retrieval_text_version") != RETRIEVAL_TEXT_VERSION
    )


def _partition_documents_for_update(
    documents: list[SkillDocument],
    existing_by_id: dict[str, dict],
) -> tuple[list[SkillDocument], int]:
    to_upsert: list[SkillDocument] = []
    unchanged_count = 0

    for document in documents:
        metadata = existing_by_id.get(document.skill_id)
        if _needs_reindex(document, metadata):
            to_upsert.append(document)
        else:
            unchanged_count += 1

    return to_upsert, unchanged_count


def index_update(config: dict) -> dict[str, object]:
    skill_paths = discover_skill_paths(config)
    client = create_client(config["chroma"]["path"])
    collection = get_collection(client, config)
    skill_id_set = {
        _build_skill_id(skill_path.parent.resolve()) for skill_path in skill_paths
    }
    existing_by_id = load_collection_metadata_map(collection)
    stale_skill_ids = [
        skill_id for skill_id in existing_by_id if skill_id not in skill_id_set
    ]

    documents = materialize_skill_documents(skill_paths, metadata_by_id=existing_by_id)
    to_upsert, unchanged_count = _partition_documents_for_update(
        documents,
        existing_by_id,
    )

    upsert_documents(collection, to_upsert, config, embed_texts=embed_texts)
    delete_documents(collection, stale_skill_ids)
    return _build_index_result(
        mode="update",
        config=config,
        scanned_documents=documents,
        indexed_documents=to_upsert,
        unchanged_count=unchanged_count,
        deleted_count=len(stale_skill_ids),
    )


def _update_index_if_configured(config: dict) -> None:
    if not config.get("indexing", {}).get("update_on_start", True):
        return
    try:
        index_update(config)
    except Exception as exc:
        if is_recoverable_collection_error(exc):
            raise_collection_rebuild_required(exc)
        raise


def _resolve_query_top_k(config: dict, top_k_override: int | None) -> int:
    configured_top_k = config["retrieval"].get("top_k", DEFAULT_TOP_K)
    return _require_positive_int(
        configured_top_k if top_k_override is None else top_k_override,
        "top_k",
    )


def _query_recommendation_candidates(
    rewritten_query: str,
    config: dict,
    top_k: int,
) -> list[RecommendCandidate]:
    try:
        results = query_collection(
            rewritten_query,
            config,
            top_k,
            embed_texts=embed_texts,
        )
    except Exception as exc:
        if is_recoverable_collection_error(exc):
            raise_collection_rebuild_required(exc)
        raise

    return build_candidates(results)


def recommend_local_skills(
    rewritten_query: str,
    config: dict,
    top_k_override: int | None = None,
) -> dict[str, object]:
    _update_index_if_configured(config)
    query_top_k = _resolve_query_top_k(config, top_k_override)
    candidates = _query_recommendation_candidates(
        rewritten_query,
        config,
        query_top_k,
    )
    return {
        "rewritten_query": rewritten_query,
        "candidates": [candidate.as_dict() for candidate in candidates],
        "selected_skills": [candidate.skill_name for candidate in candidates],
    }


def build_candidates(results: dict) -> list[RecommendCandidate]:
    metadatas = (results.get("metadatas") or [[]])[0]
    distances = (results.get("distances") or [[]])[0]
    return [
        RecommendCandidate.from_query_result(metadata, distance)
        for metadata, distance in zip(metadatas, distances, strict=False)
        if metadata
    ]


def _score_from_distance(distance: object) -> float:
    try:
        numeric_distance = float(distance)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, 1.0 - numeric_distance)
