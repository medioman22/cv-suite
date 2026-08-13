#!/usr/bin/env python3
"""Fast recruiter/communications scan of Gmail — the "email pass".

Distinct from the LinkedIn job-alert pipeline (linkedin_pipeline/): this scans
your INBOX + Sent Mail for actual recruiter/company THREADS (interview
scheduling, application replies, offers) rather than job-alert digests. Useful
as a quick "what's new that needs a human reply" check, and as the mail step in
pipeline/daily_run.sh.

Speed: instead of downloading every message in the window (slow), it fetches
HEADERS ONLY for triage (tiny), drops known newsletter/alert noise, and pulls the
full body ONLY for the handful of real recruiter/company threads. Scans Sent Mail
too — you often reply/book before the tracker knows about it.

Usage:
    EMAIL_USER=... EMAIL_PASS=...  python3 mail_scan.py [--days 4] [--bodies]

  --days N   look back N days (default 4)
  --bodies   also print the body snippet of each kept thread (one extra fetch each)

Reads YOUR OWN mailbox over IMAP. Credentials come from env only — never stored.

The NOISE / HARD_NOISE lists below are a small starter set (aggregator digests,
generic newsletters). RETUNE them to your own inbox — every account accumulates a
different set of noisy senders; add substrings as you notice them getting kept.
"""
import os, sys, imaplib, email, argparse, datetime
from email import policy
from email.utils import parsedate_to_datetime
import config as cfg

# Folders scanned, in the order that reconciliation cares about (Sent first).
FOLDERS = ['"[Gmail]/Sent Mail"', getattr(cfg, "EMAIL_FOLDER", "INBOX"), "INBOX"]

# Recruiting signal: if the SUBJECT matches, always keep (marked) even from an
# unknown sender — so a real thread never gets filtered out by an over-eager
# blocklist.
SIGNAL = (
    "interview", "availability", "application", "applying", "applied", "candidate",
    "opportunity", "next step", "schedule", "offer", "recruit", "position",
    "job description", "reach out", "chat with", "hiring", "your profile for", "invitation:",
)

# HARD noise: dropped ALWAYS, even if the subject looks like a signal — these are
# machine digests/spam whose titles contain job words ("hiring", "applied", "role")
# and would otherwise masquerade as real threads. LinkedIn job digests are handled
# by the separate linkedin_pipeline/, so they never belong in this comms triage.
HARD_NOISE = (
    "jobalerts-noreply@linkedin", "jobs-noreply@linkedin", "messages-noreply@linkedin",
    "messaging-digest-noreply@linkedin", "newsletters-noreply@linkedin",
)

# FROM substrings that are never a recruiter/company thread → dropped from triage
# (unless a SIGNAL subject overrides). LinkedIn *InMail* (hit-reply@linkedin.com) is
# kept; only alerts/newsletters/transactional/shopping are noise. Starter set —
# extend with whatever recurs in your own inbox.
NOISE = (
    # aggregators / ATS job-alert notifications
    "no-reply@adzuna", "jobs2web",
    # newsletters / product / dev
    "no-reply@leetcode",
    # shopping / finance / travel / social — pure transactional/marketing
    "no-reply@revolut", "googleplay-noreply", "ticketmaster",
    "no-reply@hire.lever",  # generic lever rejections
)


def _hdr(msg, name):
    return str(msg.get(name, "") or "")


def _fmt_date(raw):
    try:
        return parsedate_to_datetime(raw).strftime("%m-%d %H:%M")
    except Exception:
        return (raw or "")[:16]


def _body(msg):
    for p in (msg.walk() if msg.is_multipart() else [msg]):
        if p.get_content_type() == "text/plain":
            try:
                t = p.get_content()
            except Exception:
                t = (p.get_payload(decode=True) or b"").decode("utf-8", "replace")
            return " ".join(t.split())
    return ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=4)
    ap.add_argument("--bodies", action="store_true")
    args = ap.parse_args()

    user, pw = os.environ.get("EMAIL_USER"), os.environ.get("EMAIL_PASS")
    if not (user and pw):
        sys.exit("set EMAIL_USER / EMAIL_PASS in env (Gmail: App Password)")
    since = (datetime.date.today() - datetime.timedelta(days=args.days)).strftime("%d-%b-%Y")

    M = imaplib.IMAP4_SSL(getattr(cfg, "EMAIL_HOST", "imap.gmail.com"), timeout=30)
    M.login(user, pw)
    total_kept = total_noise = total_fetched = 0
    try:
        for folder in FOLDERS:
            typ, _ = M.select(folder, readonly=True)
            if typ != "OK":
                continue
            _, data = M.search(None, f"(SINCE {since})")
            nums = data[0].split()
            if not nums:
                print(f"\n===== {folder} — 0 since {since} =====")
                continue
            # ONE batched header-only fetch for the whole window (fast; no bodies).
            seq = ",".join(n.decode() for n in nums)
            _, hdrs = M.fetch(seq, "(BODY.PEEK[HEADER.FIELDS (FROM TO SUBJECT DATE)])")
            rows = []
            for part in hdrs:
                if not isinstance(part, tuple):
                    continue
                num = part[0].split()[0].decode()          # message seq number
                h = email.message_from_bytes(part[1], policy=policy.default)
                frm, to = _hdr(h, "From"), _hdr(h, "To")
                subj, date = _hdr(h, "Subject"), _hdr(h, "Date")
                who = to if "Sent" in folder else frm
                addr = frm.lower() + to.lower()
                if any(n in addr for n in HARD_NOISE):        # digests/spam: drop always
                    total_noise += 1
                    continue
                is_signal = any(s in subj.lower() for s in SIGNAL)
                if not is_signal and any(n in addr for n in NOISE):
                    total_noise += 1
                    continue
                rows.append((num, _fmt_date(date), who, subj, "*" if is_signal else " "))
            rows.sort(key=lambda r: (r[4] != "*", r[1]))     # signal rows first
            total_kept += len(rows)
            print(f"\n===== {folder} — {len(rows)} kept / {len(nums)} total (since {since}) =====")
            for num, dt, who, subj, mark in rows:
                print(f"{mark}[{dt}] {who[:48]:48} | {subj[:74]}")
                if args.bodies:
                    _, bd = M.fetch(num, "(BODY.PEEK[])")
                    total_fetched += 1
                    for p in bd:
                        if isinstance(p, tuple):
                            msg = email.message_from_bytes(p[1], policy=policy.default)
                            print("      ", _body(msg)[:400])
    finally:
        M.logout()
    extra = f", {total_fetched} bodies" if args.bodies else ""
    print(f"\n— {total_kept} kept, {total_noise} noise dropped{extra} —")


if __name__ == "__main__":
    main()
