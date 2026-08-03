#!/usr/bin/env bash
set -euo pipefail

STATE_DIR="${WEIRD_CAPTCHA_STATE_DIR:-/tmp/weird_captcha_gym}"
PORT="${WEIRD_CAPTCHA_PORT:-8787}"
TIME_MODE="${WEIRD_CAPTCHA_TIME_MODE:-live}"
START_PAUSED="${WEIRD_CAPTCHA_START_PAUSED:-0}"
WINDOW_ATTEMPTS="${WEIRD_CAPTCHA_WINDOW_ATTEMPTS:-60}"
WINDOW_POLL_SECONDS="${WEIRD_CAPTCHA_WINDOW_POLL_SECONDS:-0.5}"
GEOMETRY_ATTEMPTS="${WEIRD_CAPTCHA_GEOMETRY_ATTEMPTS:-40}"
GEOMETRY_POLL_SECONDS="${WEIRD_CAPTCHA_GEOMETRY_POLL_SECONDS:-0.25}"
if [ "$TIME_MODE" != "live" ] && [ "$TIME_MODE" != "paused" ]; then
  echo "WEIRD_CAPTCHA_TIME_MODE must be live or paused" >&2
  exit 2
fi
URL="http://127.0.0.1:${PORT}/?task=$(date +%s)&time_mode=${TIME_MODE}&start_paused=${START_PAUSED}&time_control=1"

mkdir -p "$STATE_DIR"

browser_cmd="${WEIRD_CAPTCHA_BROWSER_COMMAND:-}"
if [ -z "$browser_cmd" ]; then
  for candidate in google-chrome-stable google-chrome chromium chromium-browser firefox /snap/bin/firefox; do
    if command -v "$candidate" >/dev/null 2>&1 || [ -x "$candidate" ]; then
      browser_cmd="$candidate"
      break
    fi
  done
fi

if [ -z "$browser_cmd" ]; then
  echo "No browser command found for Weird CAPTCHA Gym." | tee -a /tmp/weird_captcha_browser.log
  exit 0
fi

launch_as_user="${WEIRD_CAPTCHA_BROWSER_USER:-}"
home_dir="${WEIRD_CAPTCHA_BROWSER_HOME:-}"
if [ -z "$launch_as_user" ]; then
  launch_as_user="root"
  home_dir="/root"
  if id ga >/dev/null 2>&1; then
    launch_as_user="ga"
    home_dir="/home/ga"
  fi
elif [ -z "$home_dir" ]; then
  home_dir="$(getent passwd "$launch_as_user" | cut -d: -f6)"
  if [ -z "$home_dir" ]; then
    echo "Cannot determine home directory for $launch_as_user." >&2
    exit 1
  fi
fi

xauth=""
for candidate in "$home_dir/.Xauthority" "/run/user/1000/gdm/Xauthority"; do
  if [ -f "$candidate" ]; then
    xauth="$candidate"
    break
  fi
done

profile_dir="$home_dir/.weird-captcha-profile"
mkdir -p "$profile_dir"
chown -R "$launch_as_user:$launch_as_user" "$profile_dir" 2>/dev/null || true

if command -v xhost >/dev/null 2>&1; then
  DISPLAY=:1 xhost +SI:localuser:"$launch_as_user" >/dev/null 2>&1 || true
fi

env_prefix="DISPLAY=:1 HOME=$home_dir"
if [ -n "$xauth" ]; then
  env_prefix="$env_prefix XAUTHORITY=$xauth"
fi

if [[ "$browser_cmd" == *firefox ]]; then
  launch="$env_prefix $browser_cmd --kiosk '$URL'"
else
  launch="$env_prefix $browser_cmd --kiosk '$URL' --force-device-scale-factor=1 --no-first-run --no-default-browser-check --disable-background-networking --disable-sync --disable-infobars --disable-session-crashed-bubble --hide-crash-restore-bubble --no-sandbox --disable-dev-shm-usage --user-data-dir='$profile_dir'"
fi

echo "Launching puzzle browser as $launch_as_user via $browser_cmd -> $URL" >> /tmp/weird_captcha_browser.log
if [ "$launch_as_user" = "root" ]; then
  nohup bash -lc "$launch" >> /tmp/weird_captcha_browser.log 2>&1 &
else
  nohup sudo -u "$launch_as_user" bash -lc "$launch" >> /tmp/weird_captcha_browser.log 2>&1 &
fi

for _ in $(seq 1 "$WINDOW_ATTEMPTS"); do
  window_id="$(DISPLAY=:1 wmctrl -lx 2>/dev/null | awk 'tolower($0) ~ /weird captcha gym/ {print $1; exit}' || true)"
  if [ -n "$window_id" ]; then
    DISPLAY=:1 wmctrl -i -r "$window_id" -b add,fullscreen,maximized_vert,maximized_horz 2>/dev/null || true
    DISPLAY=:1 wmctrl -i -a "$window_id" 2>/dev/null || true
    display_size="$(DISPLAY=:1 xdpyinfo 2>/dev/null | awk '/dimensions:/ {print $2; exit}')"
    display_width="${display_size%x*}"
    display_height="${display_size#*x}"
    if ! [[ "$display_width" =~ ^[0-9]+$ && "$display_height" =~ ^[0-9]+$ ]]; then
      echo "Puzzle browser fullscreen verification failed: display geometry unavailable." >> /tmp/weird_captcha_browser.log
      exit 1
    fi
    for _ in $(seq 1 "$GEOMETRY_ATTEMPTS"); do
      geometry="$(DISPLAY=:1 wmctrl -lG 2>/dev/null | awk -v id="$window_id" '$1 == id {print $3, $4, $5, $6; exit}' || true)"
      read -r window_x window_y window_width window_height <<< "$geometry"
      if [ "$window_x" = "0" ] && [ "$window_y" = "0" ] && \
         [ "$window_width" = "$display_width" ] && [ "$window_height" = "$display_height" ]; then
        echo "Puzzle browser fullscreen verified at ${window_width}x${window_height}+${window_x}+${window_y}." >> /tmp/weird_captcha_browser.log
        exit 0
      fi
      sleep "$GEOMETRY_POLL_SECONDS"
    done
    echo "Puzzle browser fullscreen verification failed: display=${display_width}x${display_height} window=${geometry:-missing}." >> /tmp/weird_captcha_browser.log
    exit 1
  fi
  sleep "$WINDOW_POLL_SECONDS"
done

echo "Puzzle browser window was not detected before timeout." >> /tmp/weird_captcha_browser.log
DISPLAY=:1 wmctrl -l >> /tmp/weird_captcha_browser.log 2>&1 || true
exit 1
