#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import json
import os
import shutil
from pathlib import Path

import litellm
import numpy as np
import polars as pl
from dotenv import load_dotenv

from skills_vote.skillrouter.prompt import format_query, format_skill

DATASET_ID = "pipizhao/SkillRouter-Eval-Core"
OUTPUT_DIR = Path("input/skillrouter")
RAW_DIR = OUTPUT_DIR / "raw"
PARQUET_REVISION = "refs/convert/parquet"
EMBEDDING_MODEL = "openai/SkillRouter-Embedding-0.6B"
QUERY_MAX_LEN = 2000
SKILL_DESC_MAX = 500
SKILL_BODY_MAX = 8000
EMBEDDING_MAX_LENGTH = 4096
EMBEDDING_TIMEOUT = 60
EMBEDDING_RETRIES = 3


def download(raw_dir: Path = RAW_DIR) -> None:
    raw_dir.mkdir(parents=True, exist_ok=True)
    hf_home = raw_dir / ".hf_home"
    os.environ.setdefault("HF_HOME", str(hf_home))
    os.environ.setdefault("HF_HUB_CACHE", str(hf_home / "hub"))
    os.environ.setdefault("HF_XET_CACHE", str(hf_home / "xet"))
    os.environ.setdefault("HF_HUB_DISABLE_XET", "1")

    from huggingface_hub import snapshot_download

    snapshot_download(
        repo_id=DATASET_ID,
        repo_type="dataset",
        revision=PARQUET_REVISION,
        local_dir=raw_dir,
        cache_dir=hf_home / "hub",
        allow_patterns=["hard/train/*.parquet", "tasks/train/*.parquet"],
    )
    snapshot_download(
        repo_id=DATASET_ID,
        repo_type="dataset",
        local_dir=raw_dir,
        cache_dir=hf_home / "hub",
        allow_patterns=["relevance.json"],
    )


def preprocess(raw_dir: Path = RAW_DIR, output_dir: Path = OUTPUT_DIR) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)

    hard_split_dir = raw_dir / "hard" / "train"
    tasks_split_dir = raw_dir / "tasks" / "train"
    hard_paths = sorted(hard_split_dir.glob("*.parquet"))
    hard_skills = pl.scan_parquet(hard_paths).collect()
    hard_skills.write_parquet(output_dir / "hard_skills.parquet")
    skill_names_by_id = dict(hard_skills.select("skill_id", "name").iter_rows())

    relevance = json.loads((raw_dir / "relevance.json").read_text())
    relevance_rows = []
    for task_id, entry in relevance.items():
        core_gt_ids = entry["core_gt_ids"]
        auxiliary_gt_ids = entry["auxiliary_gt_ids"]
        relevance_rows.append(
            {
                "task_id": task_id,
                "task_type": entry["task_type"],
                "core_gt_ids": core_gt_ids,
                "core_gt_names": [
                    skill_names_by_id[skill_id] for skill_id in core_gt_ids
                ],
                "auxiliary_gt_ids": auxiliary_gt_ids,
                "auxiliary_gt_names": [
                    skill_names_by_id[skill_id] for skill_id in auxiliary_gt_ids
                ],
                "relevance": [
                    {"skill_id": skill_id, "grade": grade}
                    for skill_id, grade in entry["relevance"].items()
                ],
            }
        )

    tasks = pl.read_parquet(next(tasks_split_dir.glob("*.parquet")))
    relevance_df = pl.DataFrame(relevance_rows)
    columns = [
        "task_id",
        "domain",
        "instruction_text",
        "difficulty",
        "num_skills",
        "skill_names",
        "tags",
        "task_type",
        "core_gt_ids",
        "core_gt_names",
        "auxiliary_gt_ids",
        "auxiliary_gt_names",
        "relevance",
    ]
    (
        tasks.join(relevance_df, on="task_id")
        .filter(pl.col("task_type") != "generic_only")
        .select(columns)
        .write_parquet(output_dir / "eval_tasks.parquet")
    )


async def prebuild_embeddings(
    input_dir: Path = OUTPUT_DIR,
    batch_size: int = 16,
    concurrency: int = 4,
) -> None:
    load_dotenv(".env")
    api_key = os.environ["SKILLROUTER_API_KEY"]
    api_base = os.environ["SKILLROUTER_EMBED_BASE_URL"].removesuffix("/embeddings")
    model = os.environ.get("SKILLROUTER_EMBED_MODEL", EMBEDDING_MODEL)
    semaphore = asyncio.Semaphore(concurrency)

    async def embed_batch(texts: list[str]) -> np.ndarray:
        async with semaphore:
            response = await litellm.aembedding(
                model=model,
                input=texts,
                api_key=api_key,
                api_base=api_base,
                timeout=EMBEDDING_TIMEOUT,
                max_retries=EMBEDDING_RETRIES,
                encoding_format="float",
                extra_body={"truncate_prompt_tokens": EMBEDDING_MAX_LENGTH},
            )
        return np.asarray(
            [
                item["embedding"] if isinstance(item, dict) else item.embedding
                for item in response.data
            ],
            dtype=np.float32,
        )

    def normalize(embeddings: np.ndarray) -> np.ndarray:
        norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
        return embeddings / np.clip(norms, 1e-12, None)

    async def embed_texts(name: str, texts: list[str], output_path: Path) -> None:
        shard_dir = input_dir / "embedding_shards" / name
        if output_path.exists():
            if shard_dir.exists():
                shutil.rmtree(shard_dir)
            return

        shard_dir.mkdir(parents=True, exist_ok=True)

        async def write_shard(start: int, batch: list[str]) -> None:
            shard_path = shard_dir / f"{start:06d}.npy"
            if shard_path.exists():
                return

            embeddings = normalize(await embed_batch(batch))
            tmp_path = shard_path.with_suffix(".npy.tmp")
            with tmp_path.open("wb") as file:
                np.save(file, embeddings)
            tmp_path.replace(shard_path)

        batches = [
            (i, texts[i : i + batch_size]) for i in range(0, len(texts), batch_size)
        ]
        await asyncio.gather(*(write_shard(start, batch) for start, batch in batches))

        embeddings = np.vstack(
            [np.load(path) for path in sorted(shard_dir.glob("*.npy"))]
        )
        np.save(output_path, embeddings)
        shutil.rmtree(shard_dir)

    tasks = pl.read_parquet(input_dir / "eval_tasks.parquet")
    query_texts = [
        format_query(text, max_len=QUERY_MAX_LEN)
        for text in tasks["instruction_text"].to_list()
    ]
    await embed_texts(
        "eval_query", query_texts, input_dir / "eval_query_embeddings.npy"
    )

    skills = pl.read_parquet(input_dir / "hard_skills.parquet")
    skill_texts = [
        format_skill(
            row["name"],
            row["description"],
            row["body"],
            desc_max=SKILL_DESC_MAX,
            body_max=SKILL_BODY_MAX,
        )
        for row in skills.select("name", "description", "body").iter_rows(named=True)
    ]
    await embed_texts(
        "hard_skills", skill_texts, input_dir / "hard_skills_embeddings.npy"
    )

    shard_root = input_dir / "embedding_shards"
    if shard_root.exists() and not any(shard_root.iterdir()):
        shard_root.rmdir()


def main() -> None:
    download()
    preprocess()
    asyncio.run(prebuild_embeddings())


if __name__ == "__main__":
    main()
