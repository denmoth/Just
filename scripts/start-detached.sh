#!/usr/bin/env bash
# Start Just runner + indexer under the user systemd manager (not a child of Cursor/IDE).
# No fixed --unit name so this does not clash with an existing just-runner.service file.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# Prefer distro Python so pacman PyQt6/WebEngine match the interpreter (avoid venv/shims).
if [[ -n "${PYTHON:-}" ]]; then
  PY="$PYTHON"
elif [[ -x /usr/bin/python3 ]]; then
  PY=/usr/bin/python3
else
  PY=python3
fi

_stop_old() {
  if command -v timeout >/dev/null 2>&1; then
    timeout 6 systemctl --user stop \
      just-runner.service just-indexer.service \
      krunner-enhanced.service krunner-indexer.service 2>/dev/null || true
  else
    systemctl --user stop \
      just-runner.service just-indexer.service \
      krunner-enhanced.service krunner-indexer.service 2>/dev/null || true
  fi
  systemctl --user reset-failed 2>/dev/null || true
  pkill -9 -f "${ROOT}/runner.py" 2>/dev/null || true
  pkill -9 -f "${ROOT}/indexer.py" 2>/dev/null || true
  # Stale: python3 runner.py from this repo dir (second D-Bus instance, old code)
  for pid in $(pgrep -f 'python3 runner\.py' 2>/dev/null); do
    c=$(readlink -f "/proc/$pid/cwd" 2>/dev/null || true)
    if [[ "$c" == "$ROOT" ]]; then
      kill -9 "$pid" 2>/dev/null || true
    fi
  done
  sleep 0.6
}

_systemd_start() {
  local log=$1
  local role=$2
  shift 2
  local env_args=()
  for v in DISPLAY WAYLAND_DISPLAY XAUTHORITY DBUS_SESSION_BUS_ADDRESS QT_QPA_PLATFORM; do
    if [[ -n "${!v:-}" ]]; then
      env_args+=(--setenv="$v=${!v}")
    fi
  done
  local runner_prop=()
  local desc="Just indexer"
  if [[ "$role" == runner ]]; then
    runner_prop=(-p "Environment=JUST_NO_SPAWN_INDEXER=1")
    desc="Just runner (launcher)"
  fi
  systemd-run --user \
    "${env_args[@]}" \
    "${runner_prop[@]}" \
    -p "Description=${desc}" \
    -p "WorkingDirectory=${ROOT}" \
    -p "StandardOutput=append:${log}" \
    -p "StandardError=append:${log}" \
    "$PY" "$@"
}

_fallback_setsid() {
  local log=$1
  local with_no_indexer=$2
  shift 2
  cd "$ROOT"
  if [[ "$with_no_indexer" == 1 ]]; then
    env JUST_NO_SPAWN_INDEXER=1 setsid -f "$PY" "$@" >>"$log" 2>&1 </dev/null
  else
    setsid -f "$PY" "$@" >>"$log" 2>&1 </dev/null
  fi
}

_stop_old

if command -v systemd-run >/dev/null 2>&1 && systemctl --user status >/dev/null 2>&1; then
  _systemd_start /tmp/just-runner.log runner "$ROOT/runner.py"
  _systemd_start /tmp/just-indexer.log indexer "$ROOT/indexer.py" --daemon
  echo "Started Just via systemd-run (see journal: Just runner / Just indexer)"
else
  echo "systemd-run/user session unavailable; using setsid fallback" >&2
  _fallback_setsid /tmp/just-runner.log 1 "$ROOT/runner.py"
  _fallback_setsid /tmp/just-indexer.log 0 "$ROOT/indexer.py" --daemon
  echo "Started via setsid (logs: /tmp/just-runner.log, /tmp/just-indexer.log)"
fi
