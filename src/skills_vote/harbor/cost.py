from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import litellm
from pydantic import BaseModel, ConfigDict, field_validator


class HarborCost(BaseModel):
    model_config = ConfigDict(extra="ignore")

    n_input_tokens: int = 0
    n_cache_tokens: int = 0
    n_output_tokens: int = 0
    cost_usd: float | None = None

    @field_validator(
        "n_input_tokens", "n_cache_tokens", "n_output_tokens", mode="before"
    )
    @classmethod
    def default_missing_tokens(cls, value: Any) -> Any:
        return 0 if value is None else value

    def add(self, other: HarborCost) -> None:
        self.n_input_tokens += other.n_input_tokens
        self.n_cache_tokens += other.n_cache_tokens
        self.n_output_tokens += other.n_output_tokens
        if self.cost_usd is not None:
            if other.cost_usd is None:
                self.cost_usd = None
            else:
                self.cost_usd += other.cost_usd


class SkillsVoteCost(BaseModel):
    n_input_tokens: int = 0
    n_cache_tokens: int = 0
    n_output_tokens: int = 0
    input_cost_usd_litellm: float | None = None
    output_cost_usd_litellm: float | None = None
    cache_cost_usd_litellm: float | None = None
    cost_usd_litellm: float | None = None

    @field_validator(
        "n_input_tokens", "n_cache_tokens", "n_output_tokens", mode="before"
    )
    @classmethod
    def default_missing_tokens(cls, value: Any) -> Any:
        return 0 if value is None else value

    def add(self, other: SkillsVoteCost) -> None:
        self.n_input_tokens += other.n_input_tokens
        self.n_cache_tokens += other.n_cache_tokens
        self.n_output_tokens += other.n_output_tokens
        if self.input_cost_usd_litellm is not None:
            if other.input_cost_usd_litellm is None:
                self.input_cost_usd_litellm = None
            else:
                self.input_cost_usd_litellm += other.input_cost_usd_litellm
        if self.output_cost_usd_litellm is not None:
            if other.output_cost_usd_litellm is None:
                self.output_cost_usd_litellm = None
            else:
                self.output_cost_usd_litellm += other.output_cost_usd_litellm
        if self.cache_cost_usd_litellm is not None:
            if other.cache_cost_usd_litellm is None:
                self.cache_cost_usd_litellm = None
            else:
                self.cache_cost_usd_litellm += other.cache_cost_usd_litellm
        if self.cost_usd_litellm is not None:
            if other.cost_usd_litellm is None:
                self.cost_usd_litellm = None
            else:
                self.cost_usd_litellm += other.cost_usd_litellm


def write_trial_cost(trial_dir: Path) -> tuple[HarborCost, SkillsVoteCost]:
    result_path = trial_dir / "result.json"
    config_path = trial_dir / "config.json"
    result = json.loads(result_path.read_text(encoding="utf-8"))
    config = (
        json.loads(config_path.read_text(encoding="utf-8"))
        if config_path.exists()
        else result["config"]
    )
    harbor_cost = HarborCost.model_validate(result.get("agent_result") or {})
    skills_vote_cost = SkillsVoteCost(
        n_input_tokens=harbor_cost.n_input_tokens,
        n_cache_tokens=harbor_cost.n_cache_tokens,
        n_output_tokens=harbor_cost.n_output_tokens,
    )
    model_name = config.get("agent", {}).get("model_name")
    if model_name is not None:
        try:
            prompt_cost, output_cost = litellm.cost_per_token(
                model=model_name,
                prompt_tokens=harbor_cost.n_input_tokens,
                completion_tokens=harbor_cost.n_output_tokens,
                cache_read_input_tokens=harbor_cost.n_cache_tokens,
            )
            input_cost, _ = litellm.cost_per_token(
                model=model_name,
                prompt_tokens=max(
                    harbor_cost.n_input_tokens - harbor_cost.n_cache_tokens,
                    0,
                ),
                completion_tokens=0,
                cache_read_input_tokens=0,
            )
            cache_cost = prompt_cost - input_cost
            skills_vote_cost = SkillsVoteCost(
                n_input_tokens=harbor_cost.n_input_tokens,
                n_cache_tokens=harbor_cost.n_cache_tokens,
                n_output_tokens=harbor_cost.n_output_tokens,
                input_cost_usd_litellm=input_cost,
                output_cost_usd_litellm=output_cost,
                cache_cost_usd_litellm=cache_cost,
                cost_usd_litellm=prompt_cost + output_cost,
            )
        except Exception:
            pass

    cost = {
        "harbor": harbor_cost.model_dump(),
        "skills_vote": skills_vote_cost.model_dump(),
    }
    (trial_dir / "cost.json").write_text(
        json.dumps(cost, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return harbor_cost, skills_vote_cost


def write_job_cost(
    job_dir: Path,
    *,
    require_trial: bool = False,
) -> dict[str, dict[str, Any]] | None:
    harbor_cost: HarborCost | None = None
    skills_vote_cost = SkillsVoteCost(
        input_cost_usd_litellm=0.0,
        output_cost_usd_litellm=0.0,
        cache_cost_usd_litellm=0.0,
        cost_usd_litellm=0.0,
    )
    has_trial = False

    for trial_dir in sorted(path for path in job_dir.iterdir() if path.is_dir()):
        if not (trial_dir / "result.json").exists():
            continue

        trial_harbor_cost, trial_skills_vote_cost = write_trial_cost(trial_dir)
        has_trial = True
        if harbor_cost is None:
            harbor_cost = trial_harbor_cost.model_copy()
        else:
            harbor_cost.add(trial_harbor_cost)
        skills_vote_cost.add(trial_skills_vote_cost)

    if not has_trial:
        if require_trial:
            raise RuntimeError(f"No trial result.json found under {job_dir}")
        return None

    cost = {
        "harbor": harbor_cost.model_dump(),
        "skills_vote": skills_vote_cost.model_dump(),
    }
    (job_dir / "cost.json").write_text(
        json.dumps(cost, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return cost
