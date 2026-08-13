#!/usr/bin/env bash
# One-word launch for the job-search command center.
#   ./run.sh            → build the board + start the local server + open the dashboard
#   ./run.sh --no-open  → don't auto-open the browser
#   ./run.sh --port N   → serve on a different port
#
# Picks up EMAIL_USER / EMAIL_PASS (Gmail App Password) and the ADZUNA keys from
# job_crawler/.env if you keep them there, so the "Mail run" button works too.
# (.env is git-ignored — never commit credentials.)
set -euo pipefail
cd "$(dirname "$0")"

if [ -f job_crawler/.env ]; then
  while IFS='=' read -r k v; do
    case "$k" in ''|\#*) continue ;; esac
    export "$k=$v"
  done < job_crawler/.env
fi

exec python3 ui/serve.py "$@"
