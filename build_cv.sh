#!/usr/bin/env bash
# Build a tailored CV (or all of them) to a clean deliverable PDF.
# xelatex writes cv.pdf; this renames it to "<Your Name> - CV.pdf".
#
# Set your name once so the deliverable is professionally named:
#   echo 'CANDIDATE_NAME="Jane Doe"' > candidate.env     # optional, at repo root
# (falls back to "Candidate - CV.pdf" if unset).
#
#   bash build_cv.sh applications/1_strong/260714_CH_Acme_ML_Engineer   # one
#   bash build_cv.sh all                                                # every CV
#
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"

# Optional candidate.env at repo root: CANDIDATE_NAME="Jane Doe"
[ -f "$ROOT/candidate.env" ] && . "$ROOT/candidate.env"
CANDIDATE_NAME="${CANDIDATE_NAME:-Candidate}"
DELIVERABLE="${CANDIDATE_NAME} - CV.pdf"

build_one() {
  local d="$1"
  [ -f "$d/cv.tex" ] || { echo "no cv.tex in $d" >&2; return 1; }
  ( cd "$d" && xelatex -interaction=nonstopmode cv.tex >build.log 2>&1 \
      && mv -f cv.pdf "$DELIVERABLE" )
  local pages
  pages=$(grep -o "Output written on cv.pdf ([0-9]* pages)" "$d/build.log" | grep -o "[0-9]* pages" || echo "FAIL")
  echo "[$pages] ${d#$ROOT/}"
}

if [[ "${1:-}" == "all" ]]; then
  build_one "$ROOT/master"
  for d in "$ROOT"/applications/*/*/; do
    [ -f "$d/cv.tex" ] && build_one "${d%/}"
  done
else
  build_one "${1:?usage: build_cv.sh <folder>|all}"
fi
