from __future__ import annotations

from collections.abc import Mapping

DEFAULT_RETRIEVAL_METHOD = "agentic_grep"
ALLOWED_RETRIEVAL_METHODS = {"agentic_grep", "vector"}
PLACEHOLDER_PATH_MARKERS = (
    "/path/to/your-skill-library/",
    "/absolute/path/to/",
)

ALLOWED_CONFIG_KEYS = {
    "routing",
    "retrieval",
    "retrieval_context",
    "skill_library",
    "chroma",
    "embedding",
    "indexing",
}

ALLOWED_SECTION_KEYS = {
    "routing": {"mode", "max_passes"},
    "retrieval": {"method", "top_k"},
    "retrieval_context": {"mode"},
    "skill_library": {"include", "exclude"},
    "chroma": {"path", "collection"},
    "embedding": {
        "provider",
        "model",
        "dimensions",
        "api_key_env",
        "api_key",
        "base_url",
        "extra_headers",
    },
    "indexing": {"update_on_start"},
}


def find_unsupported_config_fields(config: Mapping[str, object]) -> list[str]:
    fields: list[str] = []
    for key in sorted(str(key) for key in config):
        if key not in ALLOWED_CONFIG_KEYS:
            fields.append(key)

    for section, allowed_keys in ALLOWED_SECTION_KEYS.items():
        value = config.get(section)
        if not isinstance(value, Mapping):
            continue
        for key in sorted(str(key) for key in value):
            if key not in allowed_keys:
                fields.append(f"{section}.{key}")

    return fields


def require_supported_config_fields(config: Mapping[str, object]) -> None:
    unsupported_fields = find_unsupported_config_fields(config)
    if unsupported_fields:
        joined = ", ".join(unsupported_fields)
        raise ValueError(f"Unsupported config field(s): {joined}")


def require_supported_skill_library_fields(
    skill_library: Mapping[str, object],
) -> None:
    allowed_keys = ALLOWED_SECTION_KEYS["skill_library"]
    unsupported_fields = [
        str(key) for key in sorted(skill_library) if str(key) not in allowed_keys
    ]
    if unsupported_fields:
        joined = ", ".join(f"skill_library.{key}" for key in unsupported_fields)
        raise ValueError(f"Unsupported config field(s): {joined}")


def contains_placeholder_path(pattern: str) -> bool:
    return any(marker in pattern for marker in PLACEHOLDER_PATH_MARKERS)


def resolve_retrieval_method(raw_method: object) -> tuple[str, str | None]:
    method = str(raw_method or DEFAULT_RETRIEVAL_METHOD).strip()
    if not method:
        method = DEFAULT_RETRIEVAL_METHOD
    if method in ALLOWED_RETRIEVAL_METHODS:
        return method, None
    warning = (
        f'Unsupported retrieval.method "{method}". '
        f'Falling back to "{DEFAULT_RETRIEVAL_METHOD}".'
    )
    return DEFAULT_RETRIEVAL_METHOD, warning
