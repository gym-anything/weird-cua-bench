"""Materialize gyroscopic force experiments without changing baseline profiles."""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
import shutil

from weird_captcha_gym.tools.materialize_controlled_tasks import controlled_task

ENV_ROOT = Path(__file__).resolve().parents[1] / "environments" / "board_game_captcha_env"
BASE_DIR = ENV_ROOT / "tasks" / "board_game_captcha_seed_0001"


VARIANTS = ("rotating_tilt", "nearest_hole_gravity")


def variant_task(level: int = 5, interaction: str = "full", variant: str = "rotating_tilt") -> dict:
    if level not in range(1, 6) or interaction not in {"full", "simplified"}:
        raise ValueError("expected difficulty 1–5 and full or simplified interaction")
    controls = json.loads((ENV_ROOT / "controls.json").read_text())
    profile = copy.deepcopy(controls["difficulty"][str(level)])
    count = profile["parameters"]["lamp_count"]
    if variant == "rotating_tilt":
        profile["parameters"]["external_tilt"] = {"amplitude": 0.22, "period_ms": 14000}
        instructions = ("The board also tilts on its own. The red arrow shows this changing tilt. "
                        "Centering your control does not stop it.")
        title, variant_id = "Rotating Tilt", "rotating_external_tilt_v1"
    elif variant == "nearest_hole_gravity":
        profile["parameters"]["hole_gravity"] = 0.5
        instructions = ("Only the nearest hole pulls the ball, at half your maximum tilt strength. "
                        "The attracting hole is highlighted. Centering your control does not stop its pull.")
        title, variant_id = "Nearest-Hole Gravity", "nearest_hole_gravity_v1"
    else:
        raise ValueError(f"unknown gyroscopic variant: {variant}")
    profile["natural_language"] = f"Roll through {count} ordered lamps, avoid the wells, then reach the cup. {instructions}"
    name = f"board_game_captcha_d{level}_{interaction}_{variant}_seed_0001"
    task = controlled_task(json.loads((BASE_DIR / "task.json").read_text()),
                           mechanic_id="board_game_captcha", level=level, interaction=interaction,
                           profile=profile, task_dir_name=name)
    task["name"] += f" · {title}"
    task["metadata"]["experimental_variant"] = variant_id
    task["metadata"]["design_status"] = "experimental_pending_human_and_agent_evaluation"
    return task


def materialize(destination_root: Path, level: int = 5, interaction: str = "full", variant: str = "rotating_tilt") -> Path:
    task = variant_task(level, interaction, variant)
    name = task["id"].split("@")[0]
    destination = destination_root / name
    destination.mkdir(parents=True, exist_ok=False)
    for source in BASE_DIR.iterdir():
        if not source.is_file() or source.name == "task.json":
            continue
        target = destination / source.name
        shutil.copy2(source, target)
        if source.suffix == ".sh":
            target.write_text(target.read_text().replace(BASE_DIR.name, name))
    (destination / "task.json").write_text(json.dumps(task, indent=2) + "\n")
    return destination


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tasks-root", type=Path, required=True)
    parser.add_argument("--difficulty", type=int, choices=range(1, 6), default=5)
    parser.add_argument("--interaction", choices=("full", "simplified"), default="full")
    parser.add_argument("--variant", choices=VARIANTS, default="rotating_tilt")
    args = parser.parse_args()
    print(materialize(args.tasks_root, args.difficulty, args.interaction, args.variant))


if __name__ == "__main__":
    main()
