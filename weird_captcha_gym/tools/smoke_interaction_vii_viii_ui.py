#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image

from smoke_incubator_batch_one_ui import BENCH_ROOT, run_batch


MECHANICS = (
    "specular_lighthouse_relay",
    "wind_tunnel_seed_courier",
    "hologram_silhouette_foundry",
    "orbital_docking_customs",
    "gravity_room_freight",
    "floodgate_archive_rescue",
    "elastic_membrane_sorter",
    "pheromone_dispatch",
    "clockwork_clutch_safe",
    "marionette_checkpoint",
)


def validate_viewport_pngs(out_dir: Path) -> None:
    pngs = sorted(out_dir.glob("*.png"))
    if not pngs:
        raise AssertionError(f"Interaction VII–VIII produced no PNG evidence in {out_dir}")
    wrong = []
    for path in pngs:
        with Image.open(path) as image:
            if image.size != (1280, 720):
                wrong.append(f"{path.name}: {image.size[0]}x{image.size[1]}")
    if wrong:
        raise AssertionError("evidence must be raw 1280×720 browser captures: " + ", ".join(wrong))


def main() -> None:
    parser = argparse.ArgumentParser(description="Exercise and capture Interaction VII–VIII.")
    parser.add_argument("--out-dir", default=str(BENCH_ROOT / "evidence" / "interaction_vii_viii_difficulty_v2"))
    parser.add_argument("--port", type=int, default=8910)
    parser.add_argument("--seed-prefix", default="interaction-vii-viii-smoke")
    parser.add_argument("--mechanic", choices=MECHANICS)
    args = parser.parse_args()
    mechanics = (args.mechanic,) if args.mechanic else MECHANICS
    out_dir = Path(args.out_dir)
    run_batch(mechanics=mechanics, out_dir=out_dir, port=args.port, seed_prefix=args.seed_prefix)
    validate_viewport_pngs(out_dir)


if __name__ == "__main__":
    main()
