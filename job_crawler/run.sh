#!/bin/bash
# Daily job-crawl runner: refreshes suggestions.md and feeds ../INBOX.md.
# Runs the ATS/aggregator crawler, then the LinkedIn-email parser (no-op until
# you configure email). Logs to crawler.log next to this script.
cd "$(dirname "$0")" || exit 1
echo "===== $(date '+%Y-%m-%d %H:%M') ====="
/usr/bin/python3 crawler.py
/usr/bin/python3 linkedin_inbox.py
echo ""
