#!/usr/bin/env bash
set -euo pipefail
TASK_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
STATE_DIR="${WEIRD_CAPTCHA_STATE_DIR:-/tmp/weird_captcha_gym}"
RESOLVED_TASK="${STATE_DIR}/collision_chimes-resolved-task.json"
mkdir -p "${STATE_DIR}"
python3 /workspace/scripts/resolve_collision_chimes_task.py \
  --task-json "${TASK_DIR}/task.json" \
  --output "${RESOLVED_TASK}" \
  --time-mode "${WEIRD_CAPTCHA_TIME_MODE:-live}"
python3 /workspace/shared_scripts/setup_task.py --task-json "${RESOLVED_TASK}"
exec /workspace/shared_scripts/open_puzzle_browser.sh
