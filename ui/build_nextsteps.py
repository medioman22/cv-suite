#!/usr/bin/env python3
"""Regenerate ui/nextsteps.html from tracking/NEXT_STEPS.md.

Parses action items (grouped by ## section) and the "Recent meetings" log into the
Next Steps board. Run after editing the doc — or hit /nextsteps live (serve.py
parses the same way). Done-state is a sidecar (tracking/nextsteps_done.json),
toggled in the UI; manual drag order is a sidecar too (tracking/nextsteps_order.json).

Usage: python3 ui/build_nextsteps.py
"""
import re, json, os

HERE = os.path.dirname(__file__)
ROOT = os.path.abspath(os.path.join(HERE, ".."))
SRC = os.path.join(ROOT, "tracking", "NEXT_STEPS.md")
DONE = os.path.join(ROOT, "tracking", "nextsteps_done.json")
ORDER = os.path.join(ROOT, "tracking", "nextsteps_order.json")
TPL = os.path.join(HERE, "nextsteps.template.html")
OUT = os.path.join(HERE, "nextsteps.html")


def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:60]


def parse(text):
    """-> (groups, meetings). groups=[{section, items:[{id,title,body,status,due,ref,link}]}]"""
    try:
        done = set(json.load(open(DONE, encoding="utf-8")))
    except Exception:
        done = set()
    groups, meetings, cur = [], [], None
    for ln in text.splitlines():
        ln = ln.rstrip()
        m = re.match(r"^##\s+(.*)", ln)
        if m:
            name = m.group(1).strip()
            if name.lower().startswith("recent meetings"):
                cur = "__meet__"
            else:
                cur = {"section": name, "items": []}
                groups.append(cur)
            continue
        if not ln.startswith("- ") or cur is None:
            continue
        row = ln[2:].strip()
        if cur == "__meet__":
            parts = [p.strip() for p in row.split("|")]
            if len(parts) >= 2:
                meetings.append({"date": parts[0], "title": parts[1],
                                 "note": parts[2] if len(parts) > 2 else ""})
            continue
        # action item:  [status] **Title** | action | key:value …
        st = re.match(r"^\[(\w+)\]\s*(.*)", row)
        status = st.group(1) if st else "todo"
        rest = st.group(2) if st else row
        cells = [c.strip() for c in rest.split("|")]
        tm = re.match(r"\*\*(.*?)\*\*", cells[0])
        title = tm.group(1) if tm else cells[0]
        body, due, ref, link = "", "", "", ""
        for c in cells[1:]:
            if c.startswith("due:"):
                due = c[4:].strip()
            elif c.startswith("ref:"):
                ref = c[4:].strip()
            elif c.startswith("link:"):
                link = c[5:].strip()
            elif c:
                body = c
        iid = slug(title)
        cur["items"].append({"id": iid, "title": title, "body": body, "status": status,
                             "due": due, "ref": ref, "link": link,
                             "done": iid in done or status == "done"})
    try:
        order = json.load(open(ORDER, encoding="utf-8"))
    except Exception:
        order = {}
    for g in groups:
        saved = order.get(g["section"])
        if saved:
            # manual drag order wins: saved ids first (in that order), then any
            # items not yet in the sidecar (new items) appended, unsorted.
            pos = {iid: i for i, iid in enumerate(saved)}
            g["items"].sort(key=lambda it: pos.get(it["id"], len(saved)))
        else:
            # default: calendar-confirmed (due-dated) items float to the top,
            # nearest date first; undated items keep their doc order after.
            g["items"].sort(key=lambda it: (it["due"] == "", it["due"]))
    return groups, meetings


def main():
    groups, meetings = parse(open(SRC, encoding="utf-8").read())
    tpl = open(TPL, encoding="utf-8").read()
    tpl = tpl.replace("__GROUPS__", json.dumps(groups, ensure_ascii=False))
    tpl = tpl.replace("__MEETINGS__", json.dumps(meetings, ensure_ascii=False))
    open(OUT, "w", encoding="utf-8").write(tpl)
    n = sum(len(g["items"]) for g in groups)
    print(f"nextsteps: {n} items, {len(meetings)} meetings -> {OUT}")


if __name__ == "__main__":
    main()
