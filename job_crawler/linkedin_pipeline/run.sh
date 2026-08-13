#!/usr/bin/env bash
# LinkedIn pipeline orchestrator — runs the deterministic stages (1-3) end to end.
# The cheap-model skim (stage 3b) and powerful-model fit-check (stage 4) are driven
# from the Claude session, not here. See README.md.
#
#   EMAIL_USER=you@gmail.com EMAIL_PASS='<app password>' bash run.sh
#
set -euo pipefail
cd "$(dirname "$0")"

if [[ -z "${EMAIL_USER:-}" || -z "${EMAIL_PASS:-}" ]]; then
  echo "Set EMAIL_USER and EMAIL_PASS (Gmail App Password) first." >&2
  echo "  EMAIL_USER=you@gmail.com EMAIL_PASS='xxxx xxxx xxxx xxxx' bash run.sh" >&2
  exit 1
fi

MIN_SCORE="${MIN_SCORE:-14}"
MONTHS="${MONTHS:-3}"
DELAY="${DELAY:-6}"

echo "== Stage 1: ingest LinkedIn alert emails ==" >&2
python3 ingest.py

echo "== Stage 2: score + dedupe -> candidates ==" >&2
python3 score.py --min-score "$MIN_SCORE"

echo "== Stage 2b: surface shortlist into INBOX.md ==" >&2
python3 inbox_append.py

echo "== Stage 3: fetch + date-filter (last ${MONTHS} months) ==" >&2
echo "   (paced ${DELAY}s/req; safe to Ctrl-C and re-run — it resumes)" >&2
python3 datefilter.py --months "$MONTHS" --delay "$DELAY"

echo "" >&2
echo "Done. New LinkedIn hits are now in INBOX.md; recent.md has the date-filtered set." >&2
echo "In Claude: say 'inbox' to triage, or run the cheap-model skim on recent.json first." >&2
