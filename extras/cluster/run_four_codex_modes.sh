#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -lt 3 ] || [ "$#" -gt 4 ]; then
  echo "usage: $0 ENV_DIR TASK OUTPUT_ROOT [REMOTE_URL]" >&2
  exit 2
fi

ENV_DIR=$1
TASK=$2
OUTPUT_ROOT=$3
REMOTE_URL=${4:-}
REPO_ROOT=$(git rev-parse --show-toplevel)
PYTHON=${PYTHON:-$REPO_ROOT/.venv/bin/python}
MODEL=${MODEL:-gpt-5.6-luna}
REASONING_EFFORT=${REASONING_EFFORT:-xhigh}
STEPS=${STEPS:-100}
TIMEOUT_SEC=${TIMEOUT_SEC:-3600}
SEED=${SEED:-42}

if [ ! -x "$PYTHON" ]; then
  echo "Python environment not found at $PYTHON; install .[evaluation] first" >&2
  exit 1
fi

mkdir -p "$OUTPUT_ROOT/logs" "$OUTPUT_ROOT/summaries"

run_mode() {
  local mode=$1
  local summary=$OUTPUT_ROOT/summaries/$mode.json
  local log=$OUTPUT_ROOT/logs/$mode.log
  local agent_args
  agent_args=$(printf \
    '{"model":"%s","reasoning_effort":"%s","persist_session":true,"timeout_sec":%s}' \
    "$MODEL" "$REASONING_EFFORT" "$TIMEOUT_SEC")

  if [ -f "$summary" ]; then
    echo "$mode already has a summary; skipping"
    return 0
  fi

  local command=(
    "$PYTHON" -m weird_captcha_gym.tools.run_realtime_evaluation
    --env-dir "$ENV_DIR"
    --task "$TASK"
    --agent CodexCliAgent
    --agent-args "$agent_args"
    --temporal-mode "$mode"
    --seed "$SEED"
    --steps "$STEPS"
    --fast-io
    --episode-summary-path "$summary"
  )
  if [ -n "$REMOTE_URL" ]; then
    command+=(--remote-url "$REMOTE_URL" --remote-timeout "$TIMEOUT_SEC")
  fi
  "${command[@]}" >"$log" 2>&1
}

pids=()
modes=(paused live live_timestamped live_timestamped_execution)
for mode in "${modes[@]}"; do
  run_mode "$mode" &
  pids+=("$!")
done

status=0
for index in "${!pids[@]}"; do
  if ! wait "${pids[$index]}"; then
    echo "${modes[$index]} failed; see $OUTPUT_ROOT/logs/${modes[$index]}.log" >&2
    status=1
  fi
done
exit "$status"
