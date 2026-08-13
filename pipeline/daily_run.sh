#!/usr/bin/env bash
# Daily job-search pipeline: mail -> scrape -> backlog -> cheap-LLM triage -> report.
#
#   bash pipeline/daily_run.sh
#
# Secrets are never handled here: the Python steps auto-load job_crawler/.env
# (email/Adzuna + GEMINI_API_KEY, via config.py / each step's own loader).
# The pipeline NEVER commits or applies for anything — review tracking/DAILY_REPORT.md
# (and everything else it touched) before acting on it.
set -uo pipefail
# launchd runs with a minimal PATH — make sure your python3 is found.
export PATH="/opt/anaconda3/bin:/usr/local/bin:/usr/bin:/bin:$PATH"
REPO="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO"
LOG="tracking/pipeline.log"
ts()  { date "+%Y-%m-%d %H:%M:%S"; }

# Portable watchdog (macOS has no `timeout`): run "$@", SIGTERM after $1 seconds,
# SIGKILL 5s later if it ignores it. Returns 124 on timeout (like GNU timeout).
run_to() {
  local secs="$1"; shift
  local flag; flag="$(mktemp)"
  "$@" & local pid=$!
  ( sleep "$secs"; kill -0 "$pid" 2>/dev/null || exit
    echo 1 > "$flag"; kill -TERM "$pid" 2>/dev/null; sleep 5
    kill -0 "$pid" 2>/dev/null && kill -KILL "$pid" 2>/dev/null ) & local wd=$!
  wait "$pid" 2>/dev/null; local rc=$?
  kill "$wd" 2>/dev/null; wait "$wd" 2>/dev/null
  [ -s "$flag" ] && rc=124        # watchdog fired -> GNU-timeout-style code
  rm -f "$flag"
  return $rc
}
step() {                                   # step SECS "label" cmd...
  local secs="$1" label="$2"; shift 2
  if run_to "$secs" "$@" >>"$LOG" 2>&1; then echo "[$(ts)] OK  $label" | tee -a "$LOG"
  elif [ $? -eq 124 ]; then echo "[$(ts)] TIMEOUT $label after ${secs}s — skipped (see $LOG)" | tee -a "$LOG"
  else                      echo "[$(ts)] FAIL $label (see $LOG)" | tee -a "$LOG"; fi
}

# Per-step timeouts cap total wall time so no single hang stalls the whole run.
# Comment out any step you haven't set credentials for yet (mail/triage/salary
# steps degrade gracefully and print why they skipped, but there's no point
# waiting out their timeout every day if you know they'll no-op).
echo "[$(ts)] ===== daily_run start =====" | tee -a "$LOG"
step 180 "mail: comms scan"       python3 job_crawler/mail_scan.py --days 2
step 360 "scrape: crawler"        bash -c 'cd job_crawler && python3 crawler.py --no-inbox'
step 180 "backlog: harvest"       python3 pipeline/backlog_update.py
step 420 "enrich: title+desc"     python3 pipeline/enrich.py
step 900 "triage: cheap LLM"      python3 pipeline/triage.py
step  60 "superstar: cap"         python3 pipeline/superstar_cap.py
step 360 "salary: cache+backfill" python3 pipeline/salary.py
step 600 "refresh: posting status" python3 pipeline/refresh_status.py --cap 90
step 120 "sync: applications/ folders" python3 pipeline/sync_folders.py
echo "[$(ts)] ===== daily_run done -> tracking/DAILY_REPORT.md =====" | tee -a "$LOG"
