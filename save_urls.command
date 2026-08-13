#!/bin/bash
# Double-clickable launcher: save all open Google Chrome tabs into this repo's
# job-search inbox (tracking/INBOX.md). Filters noise, canonicalizes LinkedIn
# job links, dedups, and shows a summary dialog.
#
# Double-click it in Finder (or bind it to a Shortcut / Raycast). Grant
# Automation access to Google Chrome when macOS asks. Flags pass through
# (e.g. --no-dialog). See save_open_urls.py for how this relates to
# job_crawler/bookmarklet.md (the other, in-page capture path).
DIR="$(cd "$(dirname "$0")" && pwd)"
exec /usr/bin/python3 "$DIR/save_open_urls.py" "$@"
