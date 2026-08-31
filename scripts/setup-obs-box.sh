#!/usr/bin/env bash
# Start stock OBS as a hidden Studio runtime and apply the Runtime template.
# Does not stream. Does not print the websocket password.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

OBS_BIN="${OBS_BIN:-obs}"
DISPLAY_VALUE="${DISPLAY:-:1}"
SECRET_PATH="${HOME}/.config/desk-show/obs.env"
LOG_PATH="${HOME}/.config/obs-studio/obs-box.log"
CONFIG_YAML="${ROOT}/runtime-flight/config.local.yaml"

if ! command -v "$OBS_BIN" >/dev/null 2>&1; then
  echo "OBS is not on PATH. Install OBS Studio 28+ from ppa:obsproject/obs-studio (Ubuntu package lacks browser source)." >&2
  exit 1
fi

if [[ ! -x "${ROOT}/.venv/bin/python" ]]; then
  echo "missing ${ROOT}/.venv/bin/python" >&2
  exit 1
fi

"${ROOT}/.venv/bin/python" "${ROOT}/scripts/obs_box_config.py"

# shellcheck disable=SC1090
set -a
source "$SECRET_PATH"
set +a

if [[ -z "${OBS_WEBSOCKET_PASSWORD:-}" ]]; then
  echo "OBS_WEBSOCKET_PASSWORD did not load" >&2
  exit 1
fi
echo "OBS_WEBSOCKET_PASSWORD loaded (length ${#OBS_WEBSOCKET_PASSWORD})"

if [[ ! -f "$CONFIG_YAML" ]]; then
  cp "${ROOT}/runtime-flight/config.example.yaml" "$CONFIG_YAML"
  echo "wrote $CONFIG_YAML from example"
fi

if ! ss -ltn | grep -q ':4455 '; then
  mkdir -p "$(dirname "$LOG_PATH")"
  echo "starting OBS on DISPLAY=${DISPLAY_VALUE}"
  DISPLAY="$DISPLAY_VALUE" \
    QT_QPA_PLATFORM=xcb \
    LIBGL_ALWAYS_SOFTWARE="${LIBGL_ALWAYS_SOFTWARE:-1}" \
    GALLIUM_DRIVER="${GALLIUM_DRIVER:-llvmpipe}" \
    nohup "$OBS_BIN" \
      --disable-missing-files-check \
      --multi \
      --minimize-to-tray \
      >"$LOG_PATH" 2>&1 &
  echo $! >"${HOME}/.config/obs-studio/obs-box.pid"
fi

echo "waiting for websocket :4455"
for _ in $(seq 1 60); do
  if ss -ltn | grep -q ':4455 '; then
    break
  fi
  sleep 1
done
if ! ss -ltn | grep -q ':4455 '; then
  echo "OBS websocket did not bind :4455. last log lines:" >&2
  tail -n 40 "$LOG_PATH" >&2 || true
  exit 1
fi

export PYTHONPATH="${ROOT}/runtime-flight${PYTHONPATH:+:$PYTHONPATH}"
cd "${ROOT}/runtime-flight"
"${ROOT}/.venv/bin/python" -m runtime_flight setup-obs --config "$CONFIG_YAML"
"${ROOT}/.venv/bin/python" "${ROOT}/scripts/apply-obs-layout.py"
echo "OBS box ready. program scene=split. not streaming."
