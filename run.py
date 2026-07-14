#!/usr/bin/env python3
"""Small, human-facing launcher for Weird CUA Bench."""
from __future__ import annotations

import sys
from collections.abc import Sequence

from benchmarks.weird_captcha_gym.dashboard.server import main as dashboard_main


PUBLIC_DASHBOARD = "https://gym-anything.github.io/weird-cua-bench/"
PUBLIC_ORIGIN = "https://gym-anything.github.io"


def launcher_args(argv: Sequence[str]) -> list[str]:
    args = list(argv)
    hosted = "--hosted" in args
    if hosted:
        args.remove("--hosted")
        return [
            "--companion",
            "--allow-origin",
            PUBLIC_ORIGIN,
            "--dashboard-url",
            PUBLIC_DASHBOARD,
            "--open",
            *args,
        ]
    return ["--open", *args]


def main(argv: Sequence[str] | None = None) -> int:
    return dashboard_main(launcher_args(sys.argv[1:] if argv is None else argv))


if __name__ == "__main__":
    raise SystemExit(main())
