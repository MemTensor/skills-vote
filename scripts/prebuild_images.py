import argparse
import subprocess
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

import tomlkit
import yaml


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--cfg-path",
        type=Path,
        default=Path("scripts/configs/prebuild_images.yaml"),
    )
    parser.add_argument(
        "--preinstall-dockerfile",
        type=Path,
        default=Path("docker/Dockerfile.preinstall"),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    cfg = yaml.safe_load(args.cfg_path.read_text())
    max_workers = int(cfg["max_workers"])
    datasets = list(cfg["datasets"])
    agent_versions = {
        str(agent["name"]): str(agent["version"]) for agent in cfg["agents"]
    }
    agent_build_args = []
    for agent_name, agent_version in agent_versions.items():
        build_arg_name = f"{agent_name.replace('-', '_').upper()}_VERSION"
        agent_build_args.extend(["--build-arg", f"{build_arg_name}={agent_version}"])
    dependency_versions = {
        str(dependency["name"]): str(dependency["version"])
        for dependency in cfg["dependencies"]
    }

    for dataset_cfg in datasets:
        name = str(dataset_cfg["name"])
        version = str(dataset_cfg.get("version"))
        download_dir = Path(dataset_cfg["download_dir"]).expanduser()
        registry_url: str | None = dataset_cfg.get("registry_url")
        registry_path: str | None = dataset_cfg.get("registry_path")
        task_names: list[str] = list(dataset_cfg.get("task_names"))
        exclude_task_names: set[str] = set(dataset_cfg.get("exclude_task_names"))
        image_registry = str(dataset_cfg.get("image_registry"))
        image_tag: str | None = dataset_cfg.get("image_tag")
        resolved_image_tag = image_tag or datetime.now().strftime("%Y%m%d")

        dataset_full_name = f"{name}@{version}" if version else name
        download_cmd = [
            "uv",
            "run",
            "harbor",
            "datasets",
            "download",
            dataset_full_name,
            "--cache",
            "-o",
            str(download_dir),
        ]
        if registry_path:
            download_cmd.extend(
                ["--registry-path", str(Path(registry_path).expanduser())]
            )
        elif registry_url:
            download_cmd.extend(["--registry-url", registry_url])

        subprocess.run(download_cmd, check=True)

        task_tomls = sorted(download_dir.glob("**/task.toml"))
        if task_names:
            task_name_set = set(task_names)
            task_tomls = [p for p in task_tomls if p.parent.name in task_name_set]
        if exclude_task_names:
            task_tomls = [
                p for p in task_tomls if p.parent.name not in exclude_task_names
            ]

        preinstall_tasks = []
        writeback_tasks = []
        for task_toml in task_tomls:
            task_name = task_toml.parent.name
            doc = tomlkit.parse(task_toml.read_text())
            target_image = f"{image_registry}/{task_name}:{resolved_image_tag}"
            writeback_tasks.append((task_toml, target_image))

            image_check = subprocess.run(
                ["docker", "image", "inspect", target_image],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            if image_check.returncode == 0:
                print(f"Skipping preinstall: {target_image} already exists")
                continue

            source_image = doc["environment"].get("docker_image")
            source_build_cmd = None
            if source_image:
                source_image = str(source_image)
            else:
                source_image = f"local/{task_name}:{resolved_image_tag}"
                source_image_check = subprocess.run(
                    ["docker", "image", "inspect", source_image],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                if source_image_check.returncode != 0:
                    source_build_cmd = [
                        "docker",
                        "build",
                        "--progress=plain",
                        "-t",
                        source_image,
                        str(task_toml.parent / "environment"),
                    ]

            preinstall_cmd = [
                "docker",
                "build",
                "--progress=plain",
                "-f",
                str(args.preinstall_dockerfile),
                "--build-arg",
                f"BASE_IMAGE={source_image}",
                "--build-arg",
                f"NVM_VERSION={dependency_versions['nvm']}",
                "--build-arg",
                f"NODE_VERSION={dependency_versions['node']}",
                *agent_build_args,
                "-t",
                target_image,
                "docker",
            ]
            preinstall_tasks.append(
                (task_toml, target_image, source_build_cmd, preinstall_cmd)
            )

        if len(preinstall_tasks) == 1 or max_workers <= 1:
            for _, _, source_build_cmd, preinstall_cmd in preinstall_tasks:
                if source_build_cmd:
                    print(f"Running source build: {' '.join(source_build_cmd)}")
                    subprocess.run(source_build_cmd, check=True)
                print(f"Running preinstall: {' '.join(preinstall_cmd)}")
                subprocess.run(preinstall_cmd, check=True)
        else:
            for _, _, source_build_cmd, preinstall_cmd in preinstall_tasks:
                if source_build_cmd:
                    print(f"Running source build: {' '.join(source_build_cmd)}")
                print(f"Running preinstall: {' '.join(preinstall_cmd)}")
            with ThreadPoolExecutor(max_workers=max_workers) as pool:
                list(
                    pool.map(
                        lambda item: (
                            subprocess.run(item[2], check=True) if item[2] else None,
                            subprocess.run(item[3], check=True),
                        ),
                        preinstall_tasks,
                    )
                )

        for task_toml, target_image in writeback_tasks:
            doc = tomlkit.parse(task_toml.read_text())
            doc["environment"]["docker_image"] = target_image
            task_toml.write_text(tomlkit.dumps(doc))


if __name__ == "__main__":
    main()
