#!/usr/bin/env bash
set -euo pipefail

/workspace/shared_scripts/export_result.sh

python3 - <<'PY'
from __future__ import annotations

import json
import os
from pathlib import Path

state_dir = Path(os.environ.get("WEIRD_CAPTCHA_STATE_DIR", "/tmp/weird_captcha_gym"))
target = Path("/tmp/task_result.json")
payload = json.loads(target.read_text(encoding="utf-8"))
attempts_path = state_dir / "attempts.jsonl"
attempts = []
if attempts_path.exists():
    for line in attempts_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            value = {"_error": str(exc), "_raw": line}
        attempts.append(value)
payload["graded_attempts"] = attempts
temporary = target.with_suffix(".json.tmp")
temporary.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
os.replace(temporary, target)
target.chmod(0o666)
print(json.dumps({"ok": True, "graded_attempts": len(attempts)}))
PY
