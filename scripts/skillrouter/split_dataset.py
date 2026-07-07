#!/usr/bin/env python3
from __future__ import annotations

import random
from pathlib import Path

import polars as pl

INPUT_DIR = Path("input/skillrouter")
HARD_SKILLS_PATH = INPUT_DIR / "hard_skills.parquet"
EVAL_TASKS_PATH = INPUT_DIR / "eval_tasks.parquet"
OUTPUT_PATH = INPUT_DIR / "hard_skills_split_metadata.parquet"
SHUFFLE_SEED = 42

SPLITS = [
    {"split_id": 1, "split_name": "1k", "num_skills": 1000, "num_distractors": 100},
    {"split_id": 2, "split_name": "2k", "num_skills": 2000, "num_distractors": 200},
    {"split_id": 3, "split_name": "5k", "num_skills": 5000, "num_distractors": 500},
    {"split_id": 4, "split_name": "10k", "num_skills": 10000, "num_distractors": 780},
    {"split_id": 5, "split_name": "20k", "num_skills": 20000, "num_distractors": 780},
    {"split_id": 6, "split_name": "50k", "num_skills": 50000, "num_distractors": 780},
    {
        "split_id": 7,
        "split_name": "full",
        "num_skills": 79141,
        "num_distractors": 780,
    },
]


def main() -> None:
    skills = pl.read_parquet(HARD_SKILLS_PATH).with_row_index("skill_idx")
    tasks = pl.read_parquet(EVAL_TASKS_PATH)

    # The scored benchmark has 75 tasks. Its deduped core GT ids are fewer than
    # all skills marked as `source == "gt"` in the hard pool.
    required_ids = list(
        dict.fromkeys(
            skill_id
            for core_gt_ids in tasks["core_gt_ids"].to_list()
            for skill_id in core_gt_ids
        )
    )
    id_to_idx = dict(skills.select("skill_id", "skill_idx").iter_rows())

    skill_rows = skills.select("skill_id", "source").iter_rows(named=True)
    required_id_set = set(required_ids)
    distractor_ids = [
        row["skill_id"] for row in skill_rows if row["source"] == "distractor"
    ]
    # Remaining non-distractor skills fill the shuffled pool. This includes the
    # non-core GT skills, otherwise the full split would be short by those ids.
    pool_ids = [
        row["skill_id"]
        for row in skills.select("skill_id", "source").iter_rows(named=True)
        if row["source"] != "distractor" and row["skill_id"] not in required_id_set
    ]
    rng = random.Random(SHUFFLE_SEED)
    rng.shuffle(distractor_ids)
    rng.shuffle(pool_ids)

    rows = []
    for split in SPLITS:
        num_skills = int(split["num_skills"])
        num_distractors = int(split["num_distractors"])
        num_pool = num_skills - len(required_ids) - num_distractors
        skill_ids = (
            required_ids + distractor_ids[:num_distractors] + pool_ids[:num_pool]
        )
        rows.append(
            {
                **split,
                "skill_ids": skill_ids,
                "skill_idx": [id_to_idx[skill_id] for skill_id in skill_ids],
            }
        )

    pl.DataFrame(rows).write_parquet(OUTPUT_PATH)
    print(f"[saved] {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
