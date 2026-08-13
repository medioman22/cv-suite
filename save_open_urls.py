#!/usr/bin/env python3
"""Save every open Google Chrome tab URL straight into tracking/INBOX.md.

Self-contained: reads Chrome's open tabs itself (via `osascript`), filters out
non-job noise, canonicalizes LinkedIn job links to the /jobs/view/<id>/ form,
dedups against what INBOX.md already holds, inserts the survivors under the
"Manual / pasted" section, and reports how many landed.

This is a COMPLEMENTARY capture path to job_crawler/bookmarklet.md: the
bookmarklet grabs job links visible on the LinkedIn page you're looking at
(one page at a time, in-page); this script grabs whatever's open across ALL
your Chrome tabs and windows (useful after a browsing session where you opened
a dozen postings in tabs to look at later). Use whichever fits the moment —
they write to the same place and dedupe against each other via INBOX.md.

Usage:
    python3 save_open_urls.py              # read Chrome tabs, write INBOX, show dialog
    python3 save_open_urls.py --no-dialog  # terminal use: print summary only
    python3 save_open_urls.py --stdin      # read URLs from stdin instead of Chrome (testing)

Test against a scratch copy with:  INBOX_PATH=/tmp/INBOX.md python3 save_open_urls.py --stdin --no-dialog
"""
import sys, re, os, subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
INBOX = os.environ.get("INBOX_PATH", os.path.join(HERE, "tracking", "INBOX.md"))
SECTION = "## ✍️ Manual / pasted"


# ── Chrome tab collection ────────────────────────────────────────────────
CHROME_TABS_AS = '''
tell application "Google Chrome"
	set out to ""
	repeat with w in windows
		repeat with t in tabs of w
			set out to out & (URL of t) & linefeed
		end repeat
	end repeat
	return out
end tell
'''


def _osascript(script):
    return subprocess.run(
        ["osascript", "-e", script], capture_output=True, text=True
    )


def chrome_urls():
    """Return the list of open Chrome tab URLs, or raise RuntimeError."""
    running = _osascript('application "Google Chrome" is running').stdout.strip()
    if running != "true":
        raise RuntimeError("Google Chrome isn't running — open it and try again.")
    res = _osascript(CHROME_TABS_AS)
    if res.returncode != 0:
        hint = res.stderr.strip() or "osascript failed"
        raise RuntimeError(
            f"Couldn't read Chrome tabs ({hint}).\n"
            "Grant Automation access: System Settings → Privacy & Security → "
            "Automation → (your launcher) → Google Chrome."
        )
    return res.stdout.splitlines()


# ── URL cleaning / dedup ────────────────────────────────────────────────────
def normalize(url):
    """Return a clean job URL, or None if this tab should be dropped."""
    url = url.strip()
    if not url.startswith(("http://", "https://")):
        return None  # chrome://newtab, file://, etc.
    low = url.lower()
    if "mail.google.com" in low or "/newtab" in low or "docs.google.com" in low:
        return None  # inbox/chat/docs tabs, not jobs
    if "linkedin.com" in low:
        # keep only real job postings; drop feed/profile/messaging/browse tabs
        m = re.search(r"(?:currentjobid=|/jobs/view/)(\d+)", low)
        return f"https://www.linkedin.com/jobs/view/{m.group(1)}/" if m else None
    return url


def key(url):
    """Dedup key: LinkedIn by job id, everything else by URL sans trailing slash."""
    m = re.search(r"/jobs/view/(\d+)", url)
    return ("li", m.group(1)) if m else ("u", url.rstrip("/"))


def insert(urls):
    """Insert cleaned/deduped urls into INBOX.md. Return (added, dups, noise)."""
    with open(INBOX, encoding="utf-8") as f:
        content = f.read()
    have = {key(u) for u in re.findall(r"https?://\S+", content)}

    added, seen, dups, noise = [], set(), 0, 0
    for raw in urls:
        u = normalize(raw)
        if u is None:
            noise += 1
            continue
        k = key(u)
        if k in have or k in seen:
            dups += 1
            continue
        seen.add(k)
        added.append(u)

    if added:
        lines = content.split("\n")
        idx = next((i for i, l in enumerate(lines) if l.strip() == SECTION), None)
        if idx is None:
            at = len(lines)  # fallback: end of file
        else:
            idx += 1
            if idx < len(lines) and lines[idx].strip().startswith("_("):
                idx += 1  # place below the "_(paste links here yourself)_" note
            at = idx
        lines[at:at] = added
        with open(INBOX, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
    return added, dups, noise


def dialog(msg):
    _osascript(
        'display dialog %s buttons {"OK"} default button "OK" '
        'with title "Save open URLs → INBOX"' % _as_str(msg)
    )


def _as_str(s):
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def main():
    args = set(sys.argv[1:])
    show_dialog = "--no-dialog" not in args
    try:
        urls = sys.stdin.read().splitlines() if "--stdin" in args else chrome_urls()
    except RuntimeError as e:
        print(e, file=sys.stderr)
        if show_dialog:
            dialog(str(e))
        sys.exit(1)

    added, dups, noise = insert(urls)
    summary = f"Added {len(added)} URL(s) to INBOX.md  (skipped {dups} dup, {noise} non-job)"
    print(summary)
    if show_dialog:
        dialog(summary)


if __name__ == "__main__":
    main()
