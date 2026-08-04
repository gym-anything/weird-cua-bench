#!/usr/bin/env bash
set -euo pipefail

usage() {
  echo "Usage: $0 <interaction|difficulty|realtime> <environment_dir>" >&2
  echo "Example: $0 difficulty rotating_keyboard_env" >&2
}

if [[ $# -ne 2 ]]; then
  usage
  exit 2
fi

axis="$1"
environment="${2%/}"
environment="${environment##*/}"

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(git -C "$script_dir" rev-parse --show-toplevel)"
environment_path="weird_captcha_gym/environments/$environment"

if [[ ! -d "$repo_root/$environment_path" ]]; then
  echo "Unknown environment directory: $environment" >&2
  exit 2
fi

case "$axis" in
  interaction)
    assignment="Implement the interaction axis only. Determine whether the current interface is simplified or full. Preserve the same-seed world, information, goal, action effects, physics, timing, tolerances, and success condition while adding the missing interaction mode."
    ;;
  difficulty)
    assignment="Implement the difficulty axis only. Before assigning the current level, inspect every existing controlled reference environment's actual current task and the code that determines its visible problem and success condition. Do not use controls.json summaries as a substitute. Compare the target with approved examples at nearby levels and explain why it belongs above some and below others. Then preserve the current configuration exactly at its calibrated level and construct the other four profiles around it."
    ;;
  realtime)
    assignment="Implement the real-time axis only. Set the observation window, frame count, and play time through the shared real-time framework. Do not add live-versus-paused branches to the environment."
    ;;
  *)
    usage
    exit 2
    ;;
esac

printf -v prompt '%s\n' \
  "Implement the $axis controllability variation for $environment_path." \
  "Read AGENTS.md, weird_captcha_gym/docs/controllability-plan.md, weird_captcha_gym/docs/interaction-puzzle-field-notes.md, and every file in weird_captcha_gym/docs/controllability/ before acting." \
  "Inspect the controlled environments, including the fifteen originally starred examples, and use their control files, materializer integration, browser wiring, grader and verifier checks, and tests as working examples. Then read this environment's task, generator, browser runtime, grader, verifier, solver, and existing controls end to end while deciding its baselines and parameters independently." \
  "$assignment" \
  "Preserve the other two controllability axes. Complete the code and validate it through generation, browser interaction, grading, verification, and the relevant repository tests. Do not stop after writing a plan."

codex_bin="${CODEX_BIN:-codex}"
echo "Running GPT-5.6 Sol for $environment ($axis)"
exec "$codex_bin" exec --yolo --model gpt-5.6-sol -c 'model_reasoning_effort="xhigh"' --cd "$repo_root" "$prompt"
