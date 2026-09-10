#!/usr/bin/env bash
set -euo pipefail

# The static browser runtime is already mounted by env.json. Keep this hook
# explicit so the environment follows the standard Gym-Anything lifecycle.
test -f /workspace/shared_runtime/app/index.html
test -f /workspace/shared_scripts/setup_task.py
