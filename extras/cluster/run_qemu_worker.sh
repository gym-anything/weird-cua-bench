#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -lt 2 ] || [ "$#" -gt 3 ]; then
  echo "usage: $0 MAX_ENVS WORKER_ID [MASTER_URL]" >&2
  exit 2
fi

MAX_ENVS=$1
WORKER_ID=$2
MASTER_URL=${3:-http://127.0.0.1:5900}
REPO_ROOT=$(git rev-parse --show-toplevel)
WORKER=${WORKER:-$REPO_ROOT/.venv/bin/gym-anything-worker}
SOURCE_QEMU_CACHE=${SOURCE_QEMU_CACHE:-$HOME/.cache/gym-anything/qemu}
LOCAL_QEMU_CACHE=${LOCAL_QEMU_CACHE:-/scratch/$USER/gym-anything-qemu}
RESTART_DELAY_SECONDS=${RESTART_DELAY_SECONDS:-120}

[ -x "$WORKER" ] || { echo "worker executable not found at $WORKER" >&2; exit 1; }
[ -w /dev/kvm ] || { echo "writable /dev/kvm is required" >&2; exit 1; }
mkdir -p "$LOCAL_QEMU_CACHE"

(
  flock -x 9
  rsync -a "$SOURCE_QEMU_CACHE/" "$LOCAL_QEMU_CACHE/"
) 9>"$LOCAL_QEMU_CACHE/.stage.lock"

export CUDA_VISIBLE_DEVICES=""
export GYM_ANYTHING_QEMU_CACHE=$LOCAL_QEMU_CACHE
cd "$REPO_ROOT"

while true; do
  if "$WORKER" \
    --host 0.0.0.0 \
    --port 0 \
    --master-url "$MASTER_URL" \
    --worker-id "$WORKER_ID" \
    --max-envs "$MAX_ENVS" \
    --timeout 2700 \
    --heartbeat-interval 30 \
    --advertise-host "$(hostname -f 2>/dev/null || hostname)" \
    --must-support-runner weird_captcha,qemu; then
    status=0
  else
    status=$?
  fi
  echo "worker exited with status $status; restarting in ${RESTART_DELAY_SECONDS}s" >&2
  sleep "$RESTART_DELAY_SECONDS"
done
