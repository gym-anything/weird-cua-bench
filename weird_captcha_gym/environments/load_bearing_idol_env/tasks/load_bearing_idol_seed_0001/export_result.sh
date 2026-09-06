#!/usr/bin/env bash
set -euo pipefail

exec "${WEIRD_CAPTCHA_SHARED_SCRIPTS:-/workspace/shared_scripts}/export_result.sh"
