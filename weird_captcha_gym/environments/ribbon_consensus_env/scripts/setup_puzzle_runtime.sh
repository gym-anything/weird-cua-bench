#!/usr/bin/env bash
set -euo pipefail

# No task-specific daemon is required; the shared runner owns the browser
# server and the task hook owns challenge generation.
test -d /workspace/tasks
