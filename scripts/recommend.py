import argparse
import asyncio
import json
from pathlib import Path

import yaml
from dotenv import load_dotenv

from skills_vote.recommend import recommend

load_dotenv()

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("-c", "--config", default="scripts/configs/recommend.yaml")
    parser.add_argument(
        "-q",
        "--query",
        default="Search for today financial news and organize into a pdf and xlsx file",
        help="Input your query for recommend",
    )
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    cfg = yaml.safe_load(Path(args.config).read_text(encoding="utf-8"))
    skills_dir = Path(cfg["skills_dir"])
    output_path = Path(cfg["output_path"])
    result = await recommend(
        task=args.query,
        skills_dir=skills_dir,
        system_prompt=cfg["prompt"]["system"],
        user_prompt=cfg["prompt"]["user"],
        max_skills=cfg["prompt"]["max_skills"],
        model=cfg["agent"]["model"],
        tools=cfg["agent"]["tools"],
        max_turns=cfg["agent"]["max_turns"],
    )
    payload = {
        "task": args.query,
        "skills_dir": str(skills_dir),
        **result.model_dump(),
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
