"""Reuse the pilot's implementation-check harness without changing raw evidence."""

import importlib.util
from pathlib import Path
import sys


sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parent


def run(name):
    path = ROOT.parent / "pilot_10_2026-09-09" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"continuation_{name}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.ROOT = ROOT
    module.main()
