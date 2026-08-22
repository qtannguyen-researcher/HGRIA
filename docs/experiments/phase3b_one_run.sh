#!/usr/bin/env bash
# Phase 3B single-run driver. Does not modify application code.
# Aborts before measurement if /api/debug shows Colab/fallback or wrong flags.
set -euo pipefail

if [ "${1:-}" = "" ]; then
  echo "usage: $0 <run_index:1|2|3>" >&2
  exit 2
fi
RUN_INDEX="$1"

export PYTHONNOUSERSITE=1
unset NGROK_AUTHTOKEN || true
unset NGROK_CONFIG || true

REPO=/home/qtannguyen/projects/researcher/HGRIA
VENV=/tmp/hgria-phase3a-venv
PY="$VENV/bin/python"
BROWSER_PY=/tmp/hgria-phase3b-browser-venv/bin/python
FREEZE=/tmp/hgria-phase3b-freeze
SHA=$(git -C "$REPO" rev-parse HEAD)
RUN_ID="phase3b-local-browser-${SHA}-r${RUN_INDEX}"
RUN_DIR="$REPO/docs/experiments/run_${SHA}_r${RUN_INDEX}"

if [ -e "$RUN_DIR" ]; then
  echo "REFUSING to overwrite $RUN_DIR" >&2
  exit 3
fi

mkdir -p "$RUN_DIR"
cp "$FREEZE/HEAD" "$RUN_DIR/HEAD"
cp "$FREEZE/uname.txt" "$RUN_DIR/uname.txt"
cp "$FREEZE/pip_freeze.txt" "$RUN_DIR/pip_freeze.txt"
cp "$REPO/config/config.json" "$RUN_DIR/config.json"
cp "$FREEZE/config.sha256" "$RUN_DIR/config.sha256"
cp "$FREEZE/opencv.txt" "$RUN_DIR/opencv.txt"
cp "$FREEZE/lscpu.txt" "$RUN_DIR/lscpu.txt"
cp "$FREEZE/free.txt" "$RUN_DIR/free.txt"
cp "$FREEZE/python_version.txt" "$RUN_DIR/python_version.txt"
cp "$FREEZE/git_status.txt" "$RUN_DIR/git_status.txt"

export HGRIA_EVALUATION_MODE=true
export HGRIA_EVALUATION_PREVIEW_ENABLED=false
export HGRIA_EVALUATION_STRICT_CAMERA=true
export HGRIA_CAMERA_BROWSER_SOURCE=true
export HGRIA_INSTRUMENTATION_RUN_ID="$RUN_ID"
export HGRIA_INSTRUMENTATION_JSONL_PATH="$RUN_DIR/instrumentation.jsonl"
export HGRIA_INSTRUMENTATION_CLIENT_JSONL_PATH="$RUN_DIR/client_instrumentation.jsonl"
export HGRIA_PHASE3B_URL="http://localhost:5000/index.html?evaluation=true"
export HGRIA_PHASE3B_BROWSER_READY="$RUN_DIR/browser.ready"
export HGRIA_PHASE3B_BROWSER_LOG="$RUN_DIR/browser.log"
export DISPLAY="${DISPLAY:-:0}"
export PLAYWRIGHT_BROWSERS_PATH="/tmp/cursor-sandbox-cache/3bc0406ba71dbc7885d542eb6690e860/playwright"

{
  echo "run_id=$RUN_ID"
  echo "git_sha=$SHA"
  echo "browser_source=true"
  echo "HGRIA_EVALUATION_MODE=$HGRIA_EVALUATION_MODE"
  echo "HGRIA_EVALUATION_PREVIEW_ENABLED=$HGRIA_EVALUATION_PREVIEW_ENABLED"
  echo "HGRIA_EVALUATION_STRICT_CAMERA=$HGRIA_EVALUATION_STRICT_CAMERA"
  echo "HGRIA_CAMERA_BROWSER_SOURCE=$HGRIA_CAMERA_BROWSER_SOURCE"
  echo "HGRIA_INSTRUMENTATION_RUN_ID=$HGRIA_INSTRUMENTATION_RUN_ID"
  echo "HGRIA_INSTRUMENTATION_JSONL_PATH=$HGRIA_INSTRUMENTATION_JSONL_PATH"
  echo "HGRIA_INSTRUMENTATION_CLIENT_JSONL_PATH=$HGRIA_INSTRUMENTATION_CLIENT_JSONL_PATH"
  echo "PYTHONNOUSERSITE=$PYTHONNOUSERSITE"
  date -u +"%Y-%m-%dT%H:%M:%SZ"
  ls -la /dev/video0 /dev/video1 2>&1 || true
  echo "DISPLAY=$DISPLAY"
} > "$RUN_DIR/environment.txt"

cd "$REPO"

if ss -ltn | grep -q ':5000 '; then
  echo "PORT_5000_BUSY" >&2
  exit 4
fi

set +e
"$PY" -m backend.main > "$RUN_DIR/server.stdout.log" 2> "$RUN_DIR/server.stderr.log" &
SPID=$!
set -e
echo "$SPID" > "$RUN_DIR/server.pid"

BPID=""
cleanup() {
  if [ -n "${BPID:-}" ] && kill -0 "$BPID" 2>/dev/null; then
    kill -TERM "$BPID" 2>/dev/null || true
  fi
  if kill -0 "$SPID" 2>/dev/null; then
    kill -TERM "$SPID" 2>/dev/null || true
    for _ in $(seq 1 10); do
      kill -0 "$SPID" 2>/dev/null || break
      sleep 1
    done
    if kill -0 "$SPID" 2>/dev/null; then
      kill -KILL "$SPID" 2>/dev/null || true
    fi
  fi
  wait "$SPID" 2>/dev/null || true
  if [ -n "${BPID:-}" ]; then
    wait "$BPID" 2>/dev/null || true
  fi
  pkill -f "$VENV/bin/python -m backend.main" 2>/dev/null || true
  pkill -x ngrok 2>/dev/null || true
}
trap cleanup EXIT

DEBUG_OK=0
for t in $(seq 1 45); do
  if ! kill -0 "$SPID" 2>/dev/null; then
    echo "SERVER_EXITED_BEFORE_DEBUG after ${t}s" | tee "$RUN_DIR/status.txt"
    tail -n 80 "$RUN_DIR/server.stderr.log" || true
    exit 5
  fi
  if curl -sS --max-time 1 http://127.0.0.1:5000/api/debug > "$RUN_DIR/debug_start.json" 2>"$RUN_DIR/debug_start.err"; then
    DEBUG_OK=1
    echo "debug_ok_after_s=$t" | tee -a "$RUN_DIR/timeline.txt"
    break
  fi
  sleep 1
done

if [ "$DEBUG_OK" -ne 1 ]; then
  echo "DEBUG_TIMEOUT" | tee "$RUN_DIR/status.txt"
  exit 6
fi

"$PY" - "$RUN_DIR/debug_start.json" <<'PY'
import json, sys
path = sys.argv[1]
data = json.load(open(path, encoding="utf-8"))
cfg = data.get("config") or {}
required = {
    "colab_mode": False,
    "colab_fallback": False,
    "preview_enabled": False,
    "evaluation_mode": True,
    "dynamic_gestures_enabled": False,
    "browser_source": True,
    "strict_camera": True,
}
bad = {k: cfg.get(k) for k, v in required.items() if cfg.get(k) is not v}
if bad:
    print("INVALID_DEBUG_CONFIG", bad)
    sys.exit(7)
print("DEBUG_CONFIG_OK")
for k, v in required.items():
    print(f"{k}={cfg.get(k)}")
PY

# Confirm OpenCV is not holding the camera before the browser starts.
{
  echo "===== fuser before browser ====="
  fuser -v /dev/video0 /dev/video1 2>&1 || true
} >> "$RUN_DIR/environment.txt"

if fuser /dev/video0 2>/dev/null | grep -qw "$SPID"; then
  echo "OPENCV_HOLDING_VIDEO0" | tee "$RUN_DIR/status.txt"
  exit 10
fi

if pgrep -x ngrok >/dev/null 2>&1; then
  echo "NGROK_DETECTED_KILLING" | tee -a "$RUN_DIR/timeline.txt"
  pkill -x ngrok || true
  echo "ngrok_terminated_before_timed_window=true" >> "$RUN_DIR/environment.txt"
else
  echo "ngrok_terminated_before_timed_window=not_running" >> "$RUN_DIR/environment.txt"
fi

# Launch the real-webcam browser against the local evaluation URL.
"$BROWSER_PY" /home/qtannguyen/projects/researcher/HGRIA/docs/experiments/phase3b_open_browser.py > "$RUN_DIR/browser.stdout.log" 2> "$RUN_DIR/browser.stderr.log" &
BPID=$!
echo "$BPID" > "$RUN_DIR/browser.pid"

BROWSER_OK=0
for t in $(seq 1 40); do
  if ! kill -0 "$BPID" 2>/dev/null; then
    echo "BROWSER_EXITED after ${t}s" | tee "$RUN_DIR/status.txt"
    tail -n 80 "$RUN_DIR/browser.stderr.log" || true
    exit 11
  fi
  if [ -f "$HGRIA_PHASE3B_BROWSER_READY" ]; then
    BROWSER_OK=1
    echo "browser_ready_after_s=$t" | tee -a "$RUN_DIR/timeline.txt"
    break
  fi
  sleep 1
done

if [ "$BROWSER_OK" -ne 1 ]; then
  echo "BROWSER_TIMEOUT" | tee "$RUN_DIR/status.txt"
  exit 12
fi

# Wait until client instrumentation is producing increasing frame IDs.
FRAMES_STARTED=0
for t in $(seq 1 30); do
  if [ -f "$RUN_DIR/client_instrumentation.jsonl" ]; then
    N=$("$PY" - "$RUN_DIR/client_instrumentation.jsonl" <<'PY'
import json, sys
ids = []
with open(sys.argv[1], encoding="utf-8") as handle:
    for line in handle:
        line = line.strip()
        if not line:
            continue
        rec = json.loads(line)
        if rec.get("event") == "client_capture" and rec.get("frame_id") is not None:
            ids.append(int(rec["frame_id"]))
print(len(ids), min(ids) if ids else 0, max(ids) if ids else 0)
PY
)
    COUNT=$(echo "$N" | awk '{print $1}')
    MINID=$(echo "$N" | awk '{print $2}')
    MAXID=$(echo "$N" | awk '{print $3}')
    echo "client_frames_so_far=$COUNT min=$MINID max=$MAXID t=$t" | tee -a "$RUN_DIR/timeline.txt"
    if [ "$COUNT" -ge 5 ] && [ "$MAXID" -gt "$MINID" ]; then
      FRAMES_STARTED=1
      break
    fi
  fi
  sleep 1
done

if [ "$FRAMES_STARTED" -ne 1 ]; then
  echo "BROWSER_INSTRUMENTATION_STOPPED" | tee "$RUN_DIR/status.txt"
  curl -sS --max-time 2 http://127.0.0.1:5000/api/debug > "$RUN_DIR/debug_no_frames.json" || true
  exit 13
fi

curl -sS --max-time 2 http://127.0.0.1:5000/api/debug > "$RUN_DIR/debug_pre_warmup.json"
{
  echo "===== fuser after browser ====="
  fuser -v /dev/video0 /dev/video1 2>&1 || true
} >> "$RUN_DIR/environment.txt"

if fuser /dev/video0 2>/dev/null | grep -qw "$SPID"; then
  echo "OPENCV_HOLDING_VIDEO0_AFTER_BROWSER" | tee "$RUN_DIR/status.txt"
  exit 14
fi

# 10 s warmup. These records are discarded in analysis.
date -u +"%Y-%m-%dT%H:%M:%S.%3NZ" > "$RUN_DIR/warmup_start_utc.txt"
sleep 10
date -u +"%Y-%m-%dT%H:%M:%S.%3NZ" > "$RUN_DIR/measure_start_utc.txt"
curl -sS --max-time 2 http://127.0.0.1:5000/api/debug > "$RUN_DIR/debug_warmup_end.json"

# Measure at least 63 s; extend until >=1000 measurement-window client captures.
MEASURE_S=63
sleep "$MEASURE_S"

count_window_captures() {
  "$PY" - "$RUN_DIR/client_instrumentation.jsonl" "$RUN_DIR/measure_start_utc.txt" <<'PY'
import json, os, sys
from datetime import datetime, timezone
path, start_path = sys.argv[1], sys.argv[2]
start_raw = open(start_path, encoding="utf-8").read().strip()
start = datetime.fromisoformat(start_raw.replace("Z", "+00:00"))
n = 0
if not os.path.exists(path):
    print(0)
    raise SystemExit
with open(path, encoding="utf-8") as handle:
    for line in handle:
        line = line.strip()
        if not line:
            continue
        rec = json.loads(line)
        if rec.get("event") != "client_capture":
            continue
        wall = rec.get("wall_iso")
        if not wall:
            continue
        ts = datetime.fromisoformat(wall.replace("Z", "+00:00"))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        if ts >= start:
            n += 1
print(n)
PY
}

WINDOW_N=$(count_window_captures)
echo "client_captures_after_${MEASURE_S}s=$WINDOW_N" | tee -a "$RUN_DIR/timeline.txt"
EXTRA=0
while [ "$WINDOW_N" -lt 1000 ]; do
  EXTRA=$((EXTRA + 10))
  if [ "$EXTRA" -gt 180 ]; then
    echo "INSUFFICIENT_CLIENT_FRAMES n=$WINDOW_N extra=${EXTRA}s" | tee "$RUN_DIR/status.txt"
    date -u +"%Y-%m-%dT%H:%M:%S.%3NZ" > "$RUN_DIR/measure_end_utc.txt"
    curl -sS --max-time 2 http://127.0.0.1:5000/api/debug > "$RUN_DIR/debug_end.json" || true
    exit 15
  fi
  echo "extending_window extra=${EXTRA}s n=$WINDOW_N" | tee -a "$RUN_DIR/timeline.txt"
  sleep 10
  WINDOW_N=$(count_window_captures)
done

date -u +"%Y-%m-%dT%H:%M:%S.%3NZ" > "$RUN_DIR/measure_end_utc.txt"
curl -sS --max-time 2 http://127.0.0.1:5000/api/debug > "$RUN_DIR/debug_end.json"

# Stop browser first, then this server process only.
if [ -n "$BPID" ] && kill -0 "$BPID" 2>/dev/null; then
  kill -TERM "$BPID" 2>/dev/null || true
fi
kill -TERM "$SPID" 2>/dev/null || true
for _ in $(seq 1 15); do
  kill -0 "$SPID" 2>/dev/null || break
  sleep 1
done
if kill -0 "$SPID" 2>/dev/null; then
  kill -KILL "$SPID" 2>/dev/null || true
fi
wait "$SPID" 2>/dev/null || true
if [ -n "$BPID" ]; then
  wait "$BPID" 2>/dev/null || true
fi
trap - EXIT
pkill -x ngrok 2>/dev/null || true

if [ ! -f "$RUN_DIR/instrumentation.jsonl" ]; then
  echo "NO_SERVER_JSONL" | tee "$RUN_DIR/status.txt"
  exit 8
fi
if [ ! -f "$RUN_DIR/client_instrumentation.jsonl" ]; then
  echo "NO_CLIENT_JSONL" | tee "$RUN_DIR/status.txt"
  exit 9
fi

echo "RUN_COMPLETE r${RUN_INDEX} window_client_captures=$WINDOW_N" | tee "$RUN_DIR/status.txt"
wc -l "$RUN_DIR/instrumentation.jsonl" "$RUN_DIR/client_instrumentation.jsonl"
ls -la "$RUN_DIR"
