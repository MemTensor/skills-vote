import argparse
import asyncio
from pathlib import Path

import polars as pl
import yaml
from dotenv import load_dotenv

from skills_vote.evaluate import evaluate_skill

load_dotenv()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("-c", "--config", default="scripts/configs/evaluate.yaml")
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    cfg = yaml.safe_load(Path(args.config).read_text(encoding="utf-8"))
    skills_dir = Path(cfg["skills_dir"])
    output_path = Path(cfg["output_path"])
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("", encoding="utf-8")

    skill_dirs = sorted(skills_dir.iterdir())
    if not skill_dirs:
        raise FileNotFoundError(f"No skill directories found under: {skills_dir}")

    active_concurrency: int = cfg["num_concurrency"]
    system_prompt: str = cfg["prompt"]["system"]
    user_prompt: str = cfg["prompt"]["user"]
    model: str = cfg["agent"]["model"]
    tools: list[str] | None = cfg["agent"]["tools"]
    max_turns: int | None = cfg["agent"]["max_turns"]

    async def run(skill_dir: Path) -> None:
        evaluation = await evaluate_skill(
            skill_dir=skill_dir,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            model=model,
            tools=tools,
            max_turns=max_turns,
        )
        with output_path.open("a", encoding="utf-8") as handle:
            pl.DataFrame(
                [
                    {
                        "skill_name": skill_dir.name,
                        "skill_path": str(skill_dir.resolve()),
                        "evaluation": evaluation.model_dump(),
                    }
                ]
            ).write_ndjson(handle)
        quality_passed = all(
            value is True
            for value in (
                evaluation.consistency,
                evaluation.completeness,
                evaluation.orientation,
            )
        )
        verifiability_passed = all(
            value is True
            for value in (
                evaluation.success_verifiability,
                evaluation.environment_controllability,
                evaluation.task_constructability,
            )
        )
        print(
            f"evaluated {skill_dir.relative_to(skills_dir).as_posix()} quality={quality_passed} verifiability={verifiability_passed}"
        )

    tasks: set[asyncio.Task[None]] = set()
    for skill_dir in skill_dirs:
        tasks.add(asyncio.create_task(run(skill_dir)))
        if len(tasks) < active_concurrency:
            continue
        done, tasks = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            task.result()
    if tasks:
        done, _ = await asyncio.wait(tasks)
        for task in done:
            task.result()


if __name__ == "__main__":
    asyncio.run(main())
