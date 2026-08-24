#!/usr/bin/env bash
set -euo pipefail

: "${OUTPUT_ROOT:?set OUTPUT_ROOT to an evaluation output directory}"
: "${VLM_BASE_URL:?set VLM_BASE_URL to the model server /v1 URL}"
: "${REMOTE_URL:?set REMOTE_URL to the Gym-Anything master URL}"
: "${AGENT:?set AGENT to a bundled class name or module:Class locator}"
: "${AGENT_ARGS:?set AGENT_ARGS to a JSON object}"

REPO_ROOT=$(git rev-parse --show-toplevel)
PYTHON=${PYTHON:-$REPO_ROOT/.venv/bin/python}
PARALLEL=${PARALLEL:-20}
SEED=${SEED:-42}
STEPS=${STEPS:-100}
REQUEST_TIMEOUT_SECONDS=${REQUEST_TIMEOUT_SECONDS:-900}
REMOTE_TIMEOUT=${REMOTE_TIMEOUT:-900}

command -v jq >/dev/null || { echo "jq is required" >&2; exit 1; }
[ -x "$PYTHON" ] || { echo "Python environment not found at $PYTHON" >&2; exit 1; }
jq -e 'type == "object"' <<<"$AGENT_ARGS" >/dev/null

"$PYTHON" "$REPO_ROOT/weird_captcha_gym/tools/materialize_controlled_tasks.py" \
  --all-controlled \
  --output-root "$REPO_ROOT/weird_captcha_gym/environments"

mkdir -p "$OUTPUT_ROOT/summaries" "$OUTPUT_ROOT/logs" "$OUTPUT_ROOT/locks"
LIST=$OUTPUT_ROOT/episodes.txt

if [ ! -f "$LIST" ]; then
  : >"$LIST"
  for env_dir in "$REPO_ROOT"/weird_captcha_gym/environments/*_env; do
    env_name=$(basename "$env_dir" _env)
    for difficulty in 1 2 3 4 5; do
      for interaction in simplified full; do
        for temporal_mode in live paused; do
          task=${env_name}_d${difficulty}_${interaction}_seed_0001
          if [ ! -d "$env_dir/tasks/$task" ]; then
            echo "missing task: $env_dir/tasks/$task" >&2
            continue
          fi
          name=${env_name}_d${difficulty}_${interaction}_${temporal_mode}
          printf '%s\t%s\t%s\t%s\n' \
            "$env_dir" "$task" "$temporal_mode" "$name" >>"$LIST"
        done
      done
    done
  done
fi

run_one() {
  local env_dir=$1 task=$2 temporal_mode=$3 name=$4
  local summary=$OUTPUT_ROOT/summaries/$name.json
  local log=$OUTPUT_ROOT/logs/$name.log
  local lock=$OUTPUT_ROOT/locks/$name
  [ -f "$summary" ] && return 0
  mkdir "$lock" 2>/dev/null || return 0
  trap 'rmdir "$lock" 2>/dev/null || true' RETURN
  [ -f "$summary" ] && return 0

  local args
  args=$(jq -c --arg task_name "$name" '. + {task_name: $task_name}' <<<"$AGENT_ARGS")
  VLM_BASE_URL=$VLM_BASE_URL "$PYTHON" \
    -m weird_captcha_gym.tools.run_realtime_evaluation \
    --env-dir "$env_dir" \
    --task "$task" \
    --temporal-mode "$temporal_mode" \
    --seed "$SEED" \
    --agent "$AGENT" \
    --agent-args "$args" \
    --request-attempts 1 \
    --request-timeout-seconds "$REQUEST_TIMEOUT_SECONDS" \
    --no-play-time-limit \
    --steps "$STEPS" \
    --use-cache \
    --cache-level pre_start \
    --fast-io \
    --remote-url "$REMOTE_URL" \
    --remote-timeout "$REMOTE_TIMEOUT" \
    --episode-summary-path "$summary" \
    >"$log" 2>&1
}
export -f run_one
export OUTPUT_ROOT VLM_BASE_URL REMOTE_URL AGENT AGENT_ARGS PYTHON
export SEED STEPS REQUEST_TIMEOUT_SECONDS REMOTE_TIMEOUT

shuf "$LIST" | xargs -P "$PARALLEL" -L 1 bash -c 'run_one "$@"' _
complete=$(find "$OUTPUT_ROOT/summaries" -maxdepth 1 -type f -name '*.json' | wc -l)
total=$(wc -l <"$LIST")
echo "sweep pass complete: $complete/$total summaries"
