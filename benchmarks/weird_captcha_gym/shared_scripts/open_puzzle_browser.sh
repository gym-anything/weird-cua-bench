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
LOCK_ATTEMPTS="${WEIRD_CAPTCHA_BROWSER_LOCK_ATTEMPTS:-600}"
LOCK_POLL_SECONDS="${WEIRD_CAPTCHA_BROWSER_LOCK_POLL_SECONDS:-0.1}"
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
  firefox_profile_root="$home_dir/snap/firefox/common/.mozilla/firefox"
  if [ ! -f "$firefox_profile_root/profiles.ini" ]; then
    firefox_profile_root="$home_dir/.mozilla/firefox"
  fi
  if [ -f "$firefox_profile_root/profiles.ini" ]; then
    firefox_profile_path="$(awk -F= '
      /^Path=/ { path=$2 }
      /^Default=1$/ && path != "" { print path; exit }
      END { if (path != "") print path }
    ' "$firefox_profile_root/profiles.ini" | head -n 1)"
    if [ -n "$firefox_profile_path" ]; then
      if [[ "$firefox_profile_path" != /* ]]; then
        firefox_profile_path="$firefox_profile_root/$firefox_profile_path"
      fi
      mkdir -p "$firefox_profile_path"
      firefox_user_js="$firefox_profile_path/user.js"
      firefox_notice_pref='user_pref("datareporting.policy.dataSubmissionEnabled", false);'
      if ! grep -Fqx "$firefox_notice_pref" "$firefox_user_js" 2>/dev/null; then
        printf '%s\n' "$firefox_notice_pref" >> "$firefox_user_js"
      fi
      chown "$launch_as_user:$launch_as_user" "$firefox_profile_path" "$firefox_user_js" 2>/dev/null || true
    fi
  fi
  launch="$env_prefix $browser_cmd --kiosk '$URL'"
else
  launch="$env_prefix $browser_cmd --kiosk '$URL' --force-device-scale-factor=1 --no-first-run --no-default-browser-check --disable-background-networking --disable-sync --disable-infobars --disable-session-crashed-bubble --hide-crash-restore-bubble --no-sandbox --disable-dev-shm-usage --user-data-dir='$profile_dir'"
fi

find_puzzle_window() {
  DISPLAY=:1 wmctrl -lx 2>/dev/null | awk 'tolower($0) ~ /weird captcha gym/ {print $1; exit}' || true
}

verify_puzzle_window() {
  local window_id="$1"
  local display_size display_width display_height geometry
  local window_x window_y window_width window_height

  DISPLAY=:1 wmctrl -i -r "$window_id" -b add,fullscreen,maximized_vert,maximized_horz 2>/dev/null || true
  DISPLAY=:1 wmctrl -i -a "$window_id" 2>/dev/null || true
  display_size="$(DISPLAY=:1 xdpyinfo 2>/dev/null | awk '/dimensions:/ {print $2; exit}')"
  display_width="${display_size%x*}"
  display_height="${display_size#*x}"
  if ! [[ "$display_width" =~ ^[0-9]+$ && "$display_height" =~ ^[0-9]+$ ]]; then
    echo "Puzzle browser fullscreen verification failed: display geometry unavailable." >> /tmp/weird_captcha_browser.log
    return 1
  fi

  for _ in $(seq 1 "$GEOMETRY_ATTEMPTS"); do
    geometry="$(DISPLAY=:1 wmctrl -lG 2>/dev/null | awk -v id="$window_id" '$1 == id {print $3, $4, $5, $6; exit}' || true)"
    read -r window_x window_y window_width window_height <<< "$geometry"
    if [ "$window_x" = "0" ] && [ "$window_y" = "0" ] && \
       [ "$window_width" = "$display_width" ] && [ "$window_height" = "$display_height" ]; then
      echo "Puzzle browser fullscreen verified at ${window_width}x${window_height}+${window_x}+${window_y}." >> /tmp/weird_captcha_browser.log
      return 0
    fi
    sleep "$GEOMETRY_POLL_SECONDS"
  done

  echo "Puzzle browser fullscreen verification failed: display=${display_width}x${display_height} window=${geometry:-missing}." >> /tmp/weird_captcha_browser.log
  return 1
}

# Serialize the discovery and launch path. Two concurrent hook invocations must
# not both miss the window and start Firefox with the same profile.
lock_dir="$STATE_DIR/browser-launch.lock"
lock_acquired=0
release_launch_lock() {
  if [ "$lock_acquired" = "1" ]; then
    rm -f "$lock_dir/owner"
    rmdir "$lock_dir" 2>/dev/null || true
  fi
}
trap release_launch_lock EXIT

for _ in $(seq 1 "$LOCK_ATTEMPTS"); do
  if mkdir "$lock_dir" 2>/dev/null; then
    lock_acquired=1
    printf '%s\n' "$$" > "$lock_dir/owner"
    break
  fi
  owner_pid="$(cat "$lock_dir/owner" 2>/dev/null || true)"
  if [[ "$owner_pid" =~ ^[0-9]+$ ]] && ! kill -0 "$owner_pid" 2>/dev/null; then
    rm -f "$lock_dir/owner"
    rmdir "$lock_dir" 2>/dev/null || true
    continue
  fi
  sleep "$LOCK_POLL_SECONDS"
done
if [ "$lock_acquired" != "1" ]; then
  echo "Puzzle browser launch lock timed out." >> /tmp/weird_captcha_browser.log
  exit 1
fi

# Gym Anything can invoke the task hook twice during one reset. Once the first
# call has opened the task, the next call reuses that exact puzzle window.
existing_window_id="$(find_puzzle_window)"
if [ -n "$existing_window_id" ]; then
  echo "Reusing existing puzzle browser window $existing_window_id." >> /tmp/weird_captcha_browser.log
  verify_puzzle_window "$existing_window_id"
  exit $?
fi

echo "Launching puzzle browser as $launch_as_user via $browser_cmd -> $URL" >> /tmp/weird_captcha_browser.log
if [ "$launch_as_user" = "root" ]; then
  nohup bash -lc "$launch" >> /tmp/weird_captcha_browser.log 2>&1 &
else
  nohup sudo -u "$launch_as_user" bash -lc "$launch" >> /tmp/weird_captcha_browser.log 2>&1 &
fi

for _ in $(seq 1 "$WINDOW_ATTEMPTS"); do
  window_id="$(find_puzzle_window)"
  if [ -n "$window_id" ]; then
    verify_puzzle_window "$window_id"
    exit $?
  fi
  sleep "$WINDOW_POLL_SECONDS"
done

echo "Puzzle browser window was not detected before timeout." >> /tmp/weird_captcha_browser.log
DISPLAY=:1 wmctrl -l >> /tmp/weird_captcha_browser.log 2>&1 || true
exit 1
