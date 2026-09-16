#!/usr/bin/env bash
# Full 5-arm launch over the remaining 59 tasks (113 total - frozen 54).
# 3 LoopX arms mirror run_loopx_rerun_54_20260908.sh; plain/goal mirror
# run_goal_plain_infra_complete.sh. Task set: remaining59.txt.
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"
PY="${MR_PYTHON:-python3}"
: "${MR_MODELONLY_COMPOSE:?set MR_MODELONLY_COMPOSE to the model-only compose overlay}"
[[ -f "$MR_MODELONLY_COMPOSE" ]] || { echo "missing model-only compose overlay" >&2; exit 2; }
MODEL="${MR_MODEL:-openai/gpt-5.6-sol}"; EFFORT="${MR_EFFORT:-xhigh}"
LOOPX_ROOT="${MR_LOOPX_ROOT:-$DIR/../loopx-official-latest}"
SHA="$(git -C "$LOOPX_ROOT" rev-parse --verify HEAD | cut -c1-12)"
OUT_ROOT="$DIR/jobs/loopx-five-arms-remaining59-20260910"
LOG_ROOT="$DIR/logs/loopx-five-arms-remaining59-20260910"
mkdir -p "$OUT_ROOT" "$LOG_ROOT"
GOAL_TIMEOUT=14400; HB_SEG=7200; TURN_IDLE=7200; MULT=3.0; LOOPX_CC=2
PG_TIMEOUT=3600; PG_CC=5
TASK_TEXT="$("$PY" - "${MR_TASK_LIST:-$DIR/remaining59.txt}" <<'PY'
import sys
from pathlib import Path
from preflight_loopx_rerun import load_task_list
print("\n".join(load_task_list(Path(sys.argv[1]), 59)))
PY
)"
mapfile -t TASKS <<< "$TASK_TEXT"
TASK_LIST="$(mktemp)"
printf '%s\n' "${TASKS[@]}" > "$TASK_LIST"
PIDS=()
cleanup() {
  local pid
  for pid in "${PIDS[@]}"; do kill "$pid" 2>/dev/null || true; done
  rm -f "$TASK_LIST"
}
trap cleanup EXIT
trap 'exit 130' INT TERM
INC=(); for t in "${TASKS[@]}"; do INC+=(-i "$t"); done
echo "$(date -Is) launching 5 arms x ${#TASKS[@]} tasks -> $OUT_ROOT"

preflight_loopx() {
  local m="$1" port="$2"
  echo "$(date -Is) preflight $m (port $port)"
  "$PY" "$DIR/preflight_loopx_rerun.py" --arm "$m" --loopx-root "$LOOPX_ROOT" \
    --port "$port" --model "$MODEL" --effort "$EFFORT" --goal-timeout "$GOAL_TIMEOUT" \
    --heartbeat-segment-timeout "$HB_SEG" --turn-idle-timeout "$TURN_IDLE" \
    --agent-timeout-multiplier "$MULT" --output "$LOG_ROOT/admission-$m.json" \
    --task-list "$TASK_LIST" --expected-task-count 59 \
    >"$LOG_ROOT/preflight-$m.log" 2>&1 || { echo "$(date -Is) PREFLIGHT FAILED $m"; return 1; }
}
launch_loopx() {  # arm_mode codex_arm port
  local m="$1" arm="$2" port="$3" jobs="$OUT_ROOT/$1"; mkdir -p "$jobs"
  echo "$(date -Is) start $m"
  ( cd "$DIR"
    PIER_CUSTOM_NETWORKS=1 MR_MODELONLY_NET=1 MR_MODELONLY_HOST=127.0.0.1 MR_MODELONLY_PORT="$port" \
    MR_API_BASE="http://127.0.0.1:$port/v1" MR_AGENT=codex MR_MODEL="$MODEL" MR_EFFORT="$EFFORT" MR_REASONING_EFFORT="$EFFORT" \
    MR_CODEX_ARM="$arm" MR_LOOPX_MODE="$m" MR_LOOPX_ROOT="$LOOPX_ROOT" \
    MR_LOOPX_PROFILE_ROOT="/tmp/loopx-profile-fair54-$SHA-$m" MR_LOOPX_PREFLIGHT=0 MR_LOOPX_WEN_COMPAT=1 \
    MR_GOAL_TIMEOUT_SEC="$GOAL_TIMEOUT" MR_UPSTREAM_TIMEOUT="$GOAL_TIMEOUT" \
    MR_HEARTBEAT_SEGMENT_TIMEOUT_SEC="$HB_SEG" MR_LOOPX_TURN_IDLE_TIMEOUT_SEC="$TURN_IDLE" \
    MR_RUN_LABEL="five-arms-rem59-$m" MR_GATEWAY_PORT="$port" MR_JOBS_DIR="$jobs" \
    MR_LOG_PATH="$LOG_ROOT/gateway_calls_$m.jsonl" MR_GATEWAY_OUT="$LOG_ROOT/gateway_$m.out" \
    MR_GATEWAY_MAX_RETRIES=12 MR_GATEWAY_RETRY_BASE_SEC=5 MR_GATEWAY_RETRY_CAP_SEC=60 \
      exec ./run.sh --all "${INC[@]}" -k 1 -n "$LOOPX_CC" --agent-timeout-multiplier "$MULT"
  ) >"$LOG_ROOT/$m.log" 2>&1 &
  PIDS+=("$!")
  echo "$(date -Is) $m launched pid=${PIDS[-1]}"
}
launch_pg() {  # mode port
  local m="$1" port="$2" jobs="$OUT_ROOT/$1"; mkdir -p "$jobs"
  echo "$(date -Is) start $m (gateway $port)"
  ( cd "$DIR"
    PIER_CUSTOM_NETWORKS=1 MR_MODELONLY_NET=1 MR_MODELONLY_HOST=127.0.0.1 MR_MODELONLY_PORT="$port" \
    MR_API_BASE="http://127.0.0.1:$port/v1" MR_AGENT=codex MR_MODEL="$MODEL" MR_EFFORT="$EFFORT" MR_REASONING_EFFORT="$EFFORT" \
    MR_CODEX_ARM="$m" MR_LOOPX_MODE=x MR_LOOPX_ROOT="$LOOPX_ROOT" MR_LOOPX_PREFLIGHT=0 MR_LOOPX_WEN_COMPAT=1 \
    MR_GOAL_TIMEOUT_SEC="$PG_TIMEOUT" MR_UPSTREAM_TIMEOUT="$PG_TIMEOUT" \
    MR_RUN_LABEL="five-arms-rem59-$m" MR_GATEWAY_PORT="$port" MR_JOBS_DIR="$jobs" \
    MR_LOG_PATH="$LOG_ROOT/gateway_calls_$m.jsonl" MR_GATEWAY_OUT="$LOG_ROOT/gateway_$m.out" \
      exec ./run.sh --all "${INC[@]}" -k 1 -n "$PG_CC"
  ) >"$LOG_ROOT/$m.log" 2>&1 &
  PIDS+=("$!")
  echo "$(date -Is) $m launched pid=${PIDS[-1]}"
}
preflight_loopx ssh-goal 4411
preflight_loopx codex-cli 4412
preflight_loopx heartbeat 4413
launch_loopx ssh-goal  loopx-native            4411
launch_loopx codex-cli loopx-native-codex-cli  4412
launch_loopx heartbeat loopx-native-heartbeat  4413
launch_pg goal  4393
launch_pg plain 4394
echo "$(date -Is) all 5 arms launched; logs -> $LOG_ROOT"
status=0
for pid in "${PIDS[@]}"; do
  if wait "$pid"; then :; else status=1; fi
done
PIDS=()
if (( status )); then
  echo "$(date -Is) one or more arms failed" >&2
  exit "$status"
fi
echo "$(date -Is) all arms finished"
