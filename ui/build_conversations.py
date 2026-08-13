#!/usr/bin/env python3
"""Regenerate ui/conversations.html from tracking/CONVERSATIONS.md.

Parses the `## Conversations` entries (each `### Name · Company — <priority tag>`
with Role/Location/Status/Read fields + a Reply block) and the `## Handled
elsewhere` bullets. The page lists each thread; the suggested reply pops up on
hover. This is for the messages that can't be auto-sent (LinkedIn DMs etc.) —
open the thread, paste, tweak, send.

Usage: python3 ui/build_conversations.py
"""
import re, json, os
HERE = os.path.dirname(__file__)
SRC  = os.path.join(HERE, "..", "tracking", "CONVERSATIONS.md")
TPL  = os.path.join(HERE, "conversations.template.html")
OUT  = os.path.join(HERE, "conversations.html")

# Priority tags used in a "### Name · Company — 🎯🇨🇭" heading. RETUNE these to
# whatever tagging scheme you actually use in CONVERSATIONS.md.
PRIOS = {"🎯": "domain", "🇨🇭": "swiss", "🌍": "reloc", "💬": "warm"}


def clean(s):
    s = re.sub(r"`([^`]*)`", r"\1", s)
    s = s.replace("**", "")
    s = re.sub(r"_([^_]+)_", r"\1", s)
    return s.strip()


def field(blk, name):
    m = re.search(rf"-\s*\*\*{name}:\*\*\s*(.+)", blk)
    return clean(m.group(1)) if m else ""


def parse(path):
    txt = open(path, encoding="utf-8").read()
    m = re.search(r"## Conversations\n(.*?)(?=\n## )", txt, re.S)
    convos = []
    if m:
        for d in re.finditer(r"### (.+?)\n(.*?)(?=\n### |\Z)", m.group(1), re.S):
            head, blk = d.group(1), d.group(2)
            # head: "Name · Company — 🎯🇨🇭"  (flags are multi-codepoint → match by substring)
            tags = [v for k, v in PRIOS.items() if k in head]
            prio = "".join(k for k in PRIOS if k in head)
            head_txt = head
            for k in PRIOS:
                head_txt = head_txt.replace(k, "")
            head_txt = head_txt.rstrip(" —-")
            name, _, company = head_txt.partition("·")
            rm = re.search(r"-\s*\*\*Reply:\*\*\s*\n+(.*)", blk, re.S)
            reply = rm.group(1).strip() if rm else ""
            convos.append({
                "name": clean(name), "company": clean(company),
                "tags": tags, "prio": prio,
                "role": field(blk, "Role"), "location": field(blk, "Location"),
                "status": field(blk, "Status"), "read": field(blk, "Read"),
                "reply": reply,
            })
    # Handled-elsewhere bullets
    hm = re.search(r"## Handled elsewhere.*?\n(.*)", txt, re.S)
    handled = []
    if hm:
        for b in re.finditer(r"^-\s+(.+)", hm.group(1), re.M):
            handled.append(clean(b.group(1)))
    return convos, handled


def build():
    convos, handled = parse(SRC)
    # priority order for display
    order = {"domain": 0, "swiss": 1, "reloc": 2, "warm": 3}
    convos.sort(key=lambda c: min([order[t] for t in c["tags"]], default=9))
    tpl = open(TPL).read()
    tpl = tpl.replace("__CONVOS__", json.dumps(convos, ensure_ascii=False))
    tpl = tpl.replace("__HANDLED__", json.dumps(handled, ensure_ascii=False))
    open(OUT, "w").write(tpl)
    print(f"conversations: {len(convos)} threads, {len(handled)} handled-elsewhere -> {OUT}")


if __name__ == "__main__":
    build()
