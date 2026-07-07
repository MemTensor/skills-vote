#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import os
import time
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any

import litellm
import numpy as np
import polars as pl
import yaml
from dotenv import load_dotenv
from omegaconf import OmegaConf

from skills_vote.skillrouter.metric import (
    full_coverage_at_k,
    hit_at_k,
    recall_at_k,
)
from skills_vote.skillrouter.prompt import format_skill
from skills_vote.skillrouter.retrieve import query

INPUT_DIR = Path("input/skillrouter")
TASKS_PATH = INPUT_DIR / "eval_tasks.parquet"
SKILLS_PATH = INPUT_DIR / "hard_skills.parquet"
SPLIT_METADATA_PATH = INPUT_DIR / "hard_skills_split_metadata.parquet"
QUERY_EMBEDDINGS_PATH = INPUT_DIR / "eval_query_embeddings.npy"
SKILL_EMBEDDINGS_PATH = INPUT_DIR / "hard_skills_embeddings.npy"

DEFAULT_CONFIG_PATH = Path("scripts/configs/skillrouter/skillrouter.yaml")
DEFAULT_RERANK_MODEL = "cohere/SkillRouter-Reranker-0.6B"


def now_text() -> str:
    return datetime.now().isoformat(timespec="seconds")


def resolve_config(
    config_path: Path, overrides: list[str] | None = None
) -> dict[str, Any]:
    resolved_now = datetime.now()
    OmegaConf.register_new_resolver(
        "now",
        lambda pattern: resolved_now.strftime(pattern),
        replace=True,
    )
    cfg = OmegaConf.load(config_path)
    if overrides:
        cfg = OmegaConf.merge(cfg, OmegaConf.from_dotlist(overrides))
    data = OmegaConf.to_container(cfg, resolve=True)
    if not isinstance(data, dict):
        raise TypeError("SkillRouter config must be a mapping.")
    assert data["split_names"]
    assert int(data["metric_top_k"]) <= int(data["rerank_top_n"])
    assert int(data["rerank_top_n"]) <= int(data["retrieve_top_k"])
    return data


def write_yaml(path: Path, data: dict[str, Any]) -> None:
    tmp_path = path.with_suffix(".tmp.yaml")
    tmp_path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    tmp_path.replace(path)


def write_parquet(path: Path, rows: list[dict[str, Any]], metric_top_k: int) -> None:
    columns = [
        "task_id",
        "hit_at_1",
        f"recall_at_{metric_top_k}",
        f"fc_at_{metric_top_k}",
        "num_skills",
        "core_gt_ids",
        "auxiliary_gt_ids",
        "pred_ids",
        "embed_top_k_ids",
        "embed_top_k_scores",
        "rerank_top_n_ids",
        "rerank_top_n_scores",
        "created_at",
        "stoped_at",
    ]
    tmp_path = path.with_suffix(".tmp.parquet")
    pl.DataFrame(rows).select(columns).write_parquet(tmp_path)
    tmp_path.replace(path)


def load_or_init_rows(
    all_path: Path, tasks: pl.DataFrame, metric_top_k: int
) -> list[dict[str, Any]]:
    if all_path.exists():
        return pl.read_parquet(all_path).to_dicts()

    rows = []
    for row in tasks.iter_rows(named=True):
        rows.append(
            {
                "task_id": row["task_id"],
                "hit_at_1": None,
                f"recall_at_{metric_top_k}": None,
                f"fc_at_{metric_top_k}": None,
                "num_skills": row["num_skills"],
                "core_gt_ids": row["core_gt_ids"],
                "auxiliary_gt_ids": row["auxiliary_gt_ids"],
                "pred_ids": [],
                "embed_top_k_ids": [],
                "embed_top_k_scores": [],
                "rerank_top_n_ids": [],
                "rerank_top_n_scores": [],
                "created_at": None,
                "stoped_at": None,
            }
        )
    write_parquet(all_path, rows, metric_top_k)
    return rows


def retrieve_once(
    rows: list[dict[str, Any]],
    split: dict[str, Any],
    cfg: dict[str, Any],
    skill_ids: list[str],
) -> None:
    top_k = int(cfg["retrieve_top_k"])
    if all(len(row.get("embed_top_k_ids") or []) >= top_k for row in rows):
        return

    query_embeddings = np.load(QUERY_EMBEDDINGS_PATH)[: len(rows)]
    skill_embeddings = np.load(SKILL_EMBEDDINGS_PATH, mmap_mode="r")
    split_skill_idx = split["skill_idx"]
    split_embeddings = skill_embeddings[np.asarray(split_skill_idx, dtype=np.int64)]
    scores, indices = query(query_embeddings, split_embeddings, top_k=top_k)
    split_skill_ids = [skill_ids[idx] for idx in split_skill_idx]

    for row, row_scores, row_indices in zip(rows, scores, indices, strict=True):
        row["embed_top_k_ids"] = [split_skill_ids[idx] for idx in row_indices.tolist()]
        row["embed_top_k_scores"] = [float(score) for score in row_scores.tolist()]


async def rerank_one(
    row: dict[str, Any],
    task_by_id: dict[str, dict[str, Any]],
    skill_by_id: dict[str, dict[str, Any]],
    cfg: dict[str, Any],
    semaphore: asyncio.Semaphore,
) -> bool:
    task_id = row["task_id"]
    top_n = int(cfg["rerank_top_n"])
    metric_top_k = int(cfg["metric_top_k"])
    candidate_ids = (row.get("embed_top_k_ids") or [])[:top_n]
    documents = [
        format_skill(
            skill_by_id[skill_id]["name"],
            skill_by_id[skill_id]["description"],
            skill_by_id[skill_id]["body"],
            desc_max=500,
            body_max=2000,
        )
        for skill_id in candidate_ids
    ]
    timeout = float(cfg["rerank_timeout"])
    model = os.environ.get("SKILLROUTER_RERANK_MODEL", DEFAULT_RERANK_MODEL)
    api_key = os.environ["SKILLROUTER_API_KEY"]
    api_base = os.environ["SKILLROUTER_RERANK_BASE_URL"]

    row["created_at"] = now_text()
    try:
        async with semaphore:
            response = await asyncio.wait_for(
                litellm.arerank(
                    model=model,
                    query=task_by_id[task_id]["instruction_text"],
                    documents=documents,
                    top_n=top_n,
                    return_documents=False,
                    api_key=api_key,
                    api_base=api_base,
                    timeout=timeout,
                ),
                timeout=timeout + 5,
            )
    except Exception as exc:
        row["stoped_at"] = now_text()
        print(f"[rerank-error] {task_id}: {exc}")
        return False

    results = sorted(
        response.results or [],
        key=lambda item: float(item["relevance_score"]),
        reverse=True,
    )
    rerank_ids = [candidate_ids[int(item["index"])] for item in results]
    rerank_scores = [float(item["relevance_score"]) for item in results]
    pred_ids = rerank_ids[:metric_top_k]
    core_gt_ids = set(row["core_gt_ids"])

    row["rerank_top_n_ids"] = rerank_ids
    row["rerank_top_n_scores"] = rerank_scores
    row["pred_ids"] = pred_ids
    row["hit_at_1"] = hit_at_k(pred_ids, core_gt_ids, 1)
    row[f"recall_at_{metric_top_k}"] = recall_at_k(
        pred_ids,
        core_gt_ids,
        metric_top_k,
    )
    row[f"fc_at_{metric_top_k}"] = full_coverage_at_k(
        pred_ids,
        core_gt_ids,
        metric_top_k,
    )
    row["stoped_at"] = now_text()
    return True


def aggregate(rows: list[dict[str, Any]], metric_top_k: int) -> dict[str, float]:
    metric_keys = ["hit_at_1", f"recall_at_{metric_top_k}", f"fc_at_{metric_top_k}"]
    completed = [
        row
        for row in rows
        if row.get("pred_ids") and len(row["pred_ids"]) >= metric_top_k
    ]
    if not completed:
        return dict.fromkeys(metric_keys, 0.0)
    return {
        key: float(np.mean([row[key] for row in completed if row[key] is not None]))
        for key in metric_keys
    }


def build_stat(
    rows: list[dict[str, Any]],
    cfg: dict[str, Any],
    stat_path: Path,
    started_at: str,
    stopped_at: str,
    run_duration: float,
) -> dict[str, Any]:
    metric_top_k = int(cfg["metric_top_k"])
    previous_duration = 0.0
    if stat_path.exists():
        previous_duration = float(
            yaml.safe_load(stat_path.read_text()).get("duration", 0.0)
        )

    completed = [
        row
        for row in rows
        if row.get("pred_ids") and len(row["pred_ids"]) >= metric_top_k
    ]
    single_rows = [row for row in completed if len(row["core_gt_ids"]) == 1]
    multi_rows = [row for row in completed if len(row["core_gt_ids"]) > 1]
    return {
        "created_at": started_at,
        "stoped_at": stopped_at,
        "duration": previous_duration + run_duration,
        "num_completed_tasks": len(completed),
        "num_total_tasks": len(rows),
        "single_skill": aggregate(single_rows, metric_top_k),
        "multi_skill": aggregate(multi_rows, metric_top_k),
        "all_skill": aggregate(completed, metric_top_k),
    }


async def run_rerank(
    rows: list[dict[str, Any]],
    all_path: Path,
    tasks: pl.DataFrame,
    skills: pl.DataFrame,
    cfg: dict[str, Any],
) -> None:
    metric_top_k = int(cfg["metric_top_k"])
    top_n = int(cfg["rerank_top_n"])
    task_by_id = {row["task_id"]: row for row in tasks.iter_rows(named=True)}
    skill_by_id = {row["skill_id"]: row for row in skills.iter_rows(named=True)}
    pending_rows = [
        row
        for row in rows
        if len(row.get("embed_top_k_ids") or []) >= top_n
        and len(row.get("rerank_top_n_ids") or []) < top_n
    ]
    semaphore = asyncio.Semaphore(int(cfg["num_rerank_concurrency"]))
    persist_every = int(cfg["num_persist_batch_size"])
    completed_since_persist = 0

    futures = [
        asyncio.create_task(rerank_one(row, task_by_id, skill_by_id, cfg, semaphore))
        for row in pending_rows
    ]
    for future in asyncio.as_completed(futures):
        await future
        completed_since_persist += 1
        if completed_since_persist >= persist_every:
            write_parquet(all_path, rows, metric_top_k)
            completed_since_persist = 0

    write_parquet(all_path, rows, metric_top_k)


async def run_split(
    split_name: str,
    cfg: dict[str, Any],
    run_dir: Path,
    tasks: pl.DataFrame,
    skills: pl.DataFrame,
    split_by_name: dict[str, dict[str, Any]],
    skill_ids: list[str],
) -> None:
    started_time = time.monotonic()
    started_at = now_text()
    run_dir.mkdir(parents=True, exist_ok=True)

    config_path = run_dir / "config.yaml"
    if config_path.exists():
        cfg = resolve_config(config_path)
    else:
        write_yaml(config_path, cfg)

    metric_top_k = int(cfg["metric_top_k"])
    all_path = run_dir / "all.parquet"
    stat_path = run_dir / "stat.yaml"
    rows = load_or_init_rows(all_path, tasks, metric_top_k)

    retrieve_once(rows, split_by_name[split_name], cfg, skill_ids)
    write_parquet(all_path, rows, metric_top_k)
    await run_rerank(rows, all_path, tasks, skills, cfg)

    stopped_at = now_text()
    stat = build_stat(
        rows,
        cfg,
        stat_path,
        started_at,
        stopped_at,
        time.monotonic() - started_time,
    )
    write_yaml(stat_path, stat)
    print(f"[saved] {run_dir}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Evaluate SkillRouter retrieval + rerank."
    )
    parser.add_argument("-c", "--config", type=Path, default=DEFAULT_CONFIG_PATH)
    parser.add_argument(
        "-y",
        "--override",
        dest="overrides",
        action="append",
        default=[],
        help="OmegaConf dotlist override, for example split_names=[1k]",
    )
    return parser.parse_args()


async def main() -> None:
    load_dotenv(".env")
    args = parse_args()
    cfg = resolve_config(args.config, args.overrides)
    tasks = pl.read_parquet(TASKS_PATH)
    skills = pl.read_parquet(SKILLS_PATH)
    skill_ids = skills["skill_id"].to_list()
    split_by_name = {
        row["split_name"]: row
        for row in pl.read_parquet(SPLIT_METADATA_PATH).iter_rows(named=True)
    }

    for split_name in cfg["split_names"]:
        split_cfg = deepcopy(cfg)
        run_dir = Path(split_cfg["output_dir"]) / split_name / split_cfg["datetime"]
        await run_split(
            split_name,
            split_cfg,
            run_dir,
            tasks,
            skills,
            split_by_name,
            skill_ids,
        )


if __name__ == "__main__":
    asyncio.run(main())
