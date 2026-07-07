#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import time
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl
import yaml
from dotenv import load_dotenv
from omegaconf import OmegaConf
from openai_codex import AsyncCodex

from skills_vote.skillrouter.metric import (
    full_coverage_at_k,
    hit_at_k,
    recall_at_k,
)
from skills_vote.skillrouter.skills_vote import (
    RecommendTimeoutError,
    build_skill_workspace,
    codex_app_config,
    destroy_skill_workspace,
    prebuild_skill_root,
    read_prefix_map,
    recommend_with_codex,
)

INPUT_DIR = Path("input/skillrouter")
TASKS_PATH = INPUT_DIR / "eval_tasks.parquet"
SKILLS_PATH = INPUT_DIR / "hard_skills.parquet"
SPLIT_METADATA_PATH = INPUT_DIR / "hard_skills_split_metadata.parquet"

DEFAULT_CONFIG_PATH = Path("scripts/configs/skillrouter/skills_vote.yaml")


def now_text() -> str:
    return datetime.now().isoformat(timespec="seconds")


def resolve_config(
    config_path: Path,
    overrides: list[str] | None = None,
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
        raise TypeError("SkillsVote config must be a mapping.")
    assert data["split_names"]
    assert int(data["recommend_top_k"]) >= int(data["metric_top_k"])
    return data


def write_yaml(path: Path, data: dict[str, Any]) -> None:
    tmp_path = path.with_suffix(".tmp.yaml")
    tmp_path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    tmp_path.replace(path)


def write_parquet(path: Path, rows: list[dict[str, Any]], metric_top_k: int) -> None:
    columns = [
        "task_id",
        "session_id",
        "hit_at_1",
        f"recall_at_{metric_top_k}",
        f"fc_at_{metric_top_k}",
        "num_skills",
        "core_gt_ids",
        "auxiliary_gt_ids",
        "pred_ids",
        "retrieve_reason",
        "created_at",
        "stoped_at",
        "input_tokens",
        "cached_input_tokens",
        "output_tokens",
        "cost_usd_litellm",
    ]
    tmp_path = path.with_suffix(".tmp.parquet")
    pl.DataFrame(rows).select(columns).write_parquet(tmp_path)
    tmp_path.replace(path)


def load_or_init_rows(
    all_path: Path,
    tasks: pl.DataFrame,
    metric_top_k: int,
) -> list[dict[str, Any]]:
    if all_path.exists():
        return pl.read_parquet(all_path).to_dicts()

    rows = []
    for row in tasks.iter_rows(named=True):
        rows.append(
            {
                "task_id": row["task_id"],
                "session_id": None,
                "hit_at_1": None,
                f"recall_at_{metric_top_k}": None,
                f"fc_at_{metric_top_k}": None,
                "num_skills": row["num_skills"],
                "core_gt_ids": row["core_gt_ids"],
                "auxiliary_gt_ids": row["auxiliary_gt_ids"],
                "pred_ids": [],
                "retrieve_reason": [],
                "created_at": None,
                "stoped_at": None,
                "input_tokens": None,
                "cached_input_tokens": None,
                "output_tokens": None,
                "cost_usd_litellm": None,
            }
        )
    write_parquet(all_path, rows, metric_top_k)
    return rows


def aggregate(rows: list[dict[str, Any]], metric_top_k: int) -> dict[str, float]:
    metric_keys = ["hit_at_1", f"recall_at_{metric_top_k}", f"fc_at_{metric_top_k}"]
    completed = [row for row in rows if row.get("hit_at_1") is not None]
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

    completed = [row for row in rows if row.get("hit_at_1") is not None]
    single_rows = [row for row in completed if len(row["core_gt_ids"]) == 1]
    multi_rows = [row for row in completed if len(row["core_gt_ids"]) > 1]
    return {
        "created_at": started_at,
        "stoped_at": stopped_at,
        "duration": previous_duration + run_duration,
        "num_completed_tasks": len(completed),
        "num_total_tasks": len(rows),
        "input_tokens": sum(int(row.get("input_tokens") or 0) for row in completed),
        "cached_input_tokens": sum(
            int(row.get("cached_input_tokens") or 0) for row in completed
        ),
        "output_tokens": sum(int(row.get("output_tokens") or 0) for row in completed),
        "cost_usd_litellm": float(
            sum(float(row.get("cost_usd_litellm") or 0.0) for row in completed)
        ),
        "single_skill": aggregate(single_rows, metric_top_k),
        "multi_skill": aggregate(multi_rows, metric_top_k),
        "all_skill": aggregate(completed, metric_top_k),
    }


async def recommend_one(
    codex: AsyncCodex,
    row: dict[str, Any],
    task_by_id: dict[str, dict[str, Any]],
    cfg: dict[str, Any],
    skills_root: Path,
    prefix_map: dict[str, str],
    semaphore: asyncio.Semaphore,
) -> bool:
    task_id = row["task_id"]
    metric_top_k = int(cfg["metric_top_k"])
    timeout = float(cfg["recommend_timeout"])
    row["created_at"] = now_text()

    try:
        async with semaphore:
            result = await recommend_with_codex(
                codex,
                task_by_id[task_id],
                cfg,
                skills_root,
                prefix_map,
                timeout=timeout,
            )
    except RecommendTimeoutError as exc:
        row["session_id"] = exc.session_id
        row["stoped_at"] = now_text()
        print(f"[recommend-error] {task_id}: {exc}")
        return False
    except Exception as exc:
        row["stoped_at"] = now_text()
        print(f"[recommend-error] {task_id}: {exc}")
        return False

    pred_ids = result["pred_ids"][:metric_top_k]
    retrieve_reason = result["retrieve_reason"][:metric_top_k]
    core_gt_ids = set(row["core_gt_ids"])

    row.update(result)
    row["pred_ids"] = pred_ids
    row["retrieve_reason"] = retrieve_reason
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


async def run_recommend(
    rows: list[dict[str, Any]],
    all_path: Path,
    tasks: pl.DataFrame,
    cfg: dict[str, Any],
    run_dir: Path,
) -> None:
    metric_top_k = int(cfg["metric_top_k"])
    pending_rows = [row for row in rows if row.get("hit_at_1") is None]
    if not pending_rows:
        return

    semaphore = asyncio.Semaphore(int(cfg["num_recommend_concurrency"]))
    persist_every = int(cfg["num_persist_batch_size"])
    completed_since_persist = 0
    task_by_id = {row["task_id"]: row for row in tasks.iter_rows(named=True)}
    skills_root = Path(cfg["codex_workspace"])
    prefix_map = read_prefix_map(Path(cfg["skill_root"]))

    async with AsyncCodex(config=codex_app_config(run_dir / ".codex", cfg)) as codex:
        futures = [
            asyncio.create_task(
                recommend_one(
                    codex,
                    row,
                    task_by_id,
                    cfg,
                    skills_root,
                    prefix_map,
                    semaphore,
                )
            )
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
    split_by_name: dict[str, dict[str, Any]],
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

    build_skill_workspace(
        split_by_name[split_name]["skill_ids"],
        Path(cfg["skill_root"]),
        Path(cfg["codex_workspace"]),
    )
    try:
        await run_recommend(rows, all_path, tasks, cfg, run_dir)
    finally:
        destroy_skill_workspace(Path(cfg["codex_workspace"]))

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
        description="Evaluate SkillsVote agentic recommend."
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
    split_by_name = {
        row["split_name"]: row
        for row in pl.read_parquet(SPLIT_METADATA_PATH).iter_rows(named=True)
    }

    prebuild_skill_root(skills, Path(cfg["skill_root"]))
    for split_name in cfg["split_names"]:
        split_cfg = deepcopy(cfg)
        run_dir = Path(split_cfg["output_dir"]) / split_name / split_cfg["datetime"]
        await run_split(split_name, split_cfg, run_dir, tasks, split_by_name)


if __name__ == "__main__":
    asyncio.run(main())
