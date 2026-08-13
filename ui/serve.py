#!/usr/bin/env python3
"""Local control-panel server for the job-search dashboard.

Serves ui/dashboard.html (the board) plus three optional pages that read other
tracking/*.md docs — ui/applications.html (tracking/APPLICATIONS.md),
ui/nextsteps.html (tracking/NEXT_STEPS.md), ui/conversations.html
(tracking/CONVERSATIONS.md) — and exposes a tiny API so the dashboard buttons
can actually run the pipeline on your machine and stream the output live.
Binds to localhost only, and only runs a fixed allow-list of commands — no
arbitrary shell.

    python3 ui/serve.py            # then open http://localhost:8765
    EMAIL_USER=you@gmail.com EMAIL_PASS='app pw' python3 ui/serve.py   # to enable the mail run

Stdlib only.
"""
import os, sys, re, json, shutil, subprocess, threading, webbrowser, argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs
from inbox_parse import parse_inbox
import build_applications

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
CRAWLER = os.path.join(ROOT, "job_crawler")
PIPE = os.path.join(CRAWLER, "linkedin_pipeline")

# Fixed allow-list: task -> (argv, cwd). No user input reaches the shell.
TASKS = {
    "scrape":       (["python3", "crawler.py"], CRAWLER),
    "mail":         (["bash", "run.sh"], PIPE),
    "build":        (["bash", "build_cv.sh", "all"], ROOT),
    "regenerate":   (["python3", os.path.join("ui", "build_dashboard.py")], ROOT),
    "applications": (["python3", os.path.join("ui", "build_applications.py")], ROOT),
    "nextsteps":    (["python3", os.path.join("ui", "build_nextsteps.py")], ROOT),
    "conversations": (["python3", os.path.join("ui", "build_conversations.py")], ROOT),
}

# Editing APPLICATIONS.md's Pipeline table from the UI (Applications page).
STAGE_OPTS = ["applied", "interviewing", "offer", "rejected", "withdrawn"]


def _clean_md(s):
    """Same normalization build_applications.py's clean() does, for matching."""
    s = re.sub(r"`([^`]*)`", r"\1", s or "")
    s = s.replace("**", "")
    s = re.sub(r"_([^_]+)_", r"\1", s)
    return re.sub(r"\s+", " ", s).strip()


def _move_to_applied(folder_rel):
    """Move an application folder into applications/0_applied/ (fit-tier folders
    are for not-yet-applied roles; 0_applied is where submitted ones live).
    Returns the new relative folder path, or None if there's nothing to do /
    it's not safe to move (outside applications/, missing, or a name collision)."""
    if not folder_rel:
        return None
    apps = os.path.realpath(os.path.join(ROOT, "applications"))
    src = os.path.realpath(os.path.join(ROOT, folder_rel))
    if not (src == apps or src.startswith(apps + os.sep)) or not os.path.isdir(src):
        return None
    dest_dir = os.path.join(ROOT, "applications", "0_applied")
    if os.path.realpath(os.path.dirname(src)) == os.path.realpath(dest_dir):
        return folder_rel  # already there
    dest = os.path.join(dest_dir, os.path.basename(src))
    if os.path.exists(dest):
        return None  # name collision — leave it where it is, don't clobber
    os.makedirs(dest_dir, exist_ok=True)
    shutil.move(src, dest)
    return os.path.relpath(dest, ROOT)


def parse_applications():
    """Live parse of tracking/APPLICATIONS.md + tracking/JOBS.md — pipeline +
    contacts + drafts, for the Applications UI. Same shape build_applications.py
    writes into applications.html at build time."""
    path = os.path.join(ROOT, "tracking", "APPLICATIONS.md")
    _, contacts = build_applications.parse(path)
    drafts = build_applications.parse_drafts(path)
    try:
        pipeline = build_applications.merged_pipeline()
    except Exception as e:
        print("  [applications] merge failed:", e)
        pipeline, _ = build_applications.parse(path)
    return pipeline, contacts, drafts


def parse_jobs():
    """Live parse of tracking/JOBS.md — same shape the dashboard expects."""
    rows = []
    path = os.path.join(ROOT, "tracking", "JOBS.md")
    for ln in open(path, encoding="utf-8"):
        if not ln.startswith("|"):
            continue
        c = [x.strip() for x in ln.strip().strip("|").split("|")]
        if len(c) < 8 or c[0] in ("#", "---") or set(c[0]) <= set("-") or c[1] in ("Company", ""):
            continue
        _, company, role, location, fit, status, folder, notes = c[:8]
        stars = fit.count("★")
        tier = {3: "strong", 2: "moderate", 1: "reach", 0: "skip"}.get(stars, "skip")
        if ("—" in fit or fit == "") and "internal" in status:
            tier = "internal"
        m = re.search(r"/[0-9]{6}_([A-Z]{2,3})_", folder)
        ms = re.search(r"_\(([^)]+)\)_\s*$", notes)
        fp = re.search(r"`([^`]+)`", folder)
        rows.append({
            "company": company.replace("⚠️defense", "").strip(), "defense": "defense" in company,
            "role": role.replace("**", ""), "location": location.replace("🇨🇭", "").replace("**", "").strip(),
            "loc": m.group(1) if m else "", "stars": stars, "tier": tier,
            "status": status.replace("**", ""), "folder": fp.group(1) if fp else folder,
            "notes": re.sub(r"_\([^)]+\)_\s*$", "", notes).replace("**", "").strip(),
            "source": ms.group(1) if ms else "",
        })
    return rows


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass  # quiet

    def _send(self, code, body, ctype="application/json"):
        b = body if isinstance(body, bytes) else body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(b)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        u = urlparse(self.path)
        if u.path in ("/", "/index.html", "/dashboard.html"):
            f = os.path.join(HERE, "dashboard.html")
            if not os.path.exists(f):
                return self._send(404, "Run `python3 ui/build_dashboard.py` first.", "text/plain")
            return self._send(200, open(f, "rb").read(), "text/html; charset=utf-8")
        if u.path in ("/applications", "/applications.html"):
            f = os.path.join(HERE, "applications.html")
            if not os.path.exists(f):
                return self._send(404, "Run `python3 ui/build_applications.py` first.", "text/plain")
            return self._send(200, open(f, "rb").read(), "text/html; charset=utf-8")
        if u.path in ("/conversations", "/conversations.html"):
            f = os.path.join(HERE, "conversations.html")
            if not os.path.exists(f):
                return self._send(404, "Run `python3 ui/build_conversations.py` first (needs tracking/CONVERSATIONS.md).", "text/plain")
            return self._send(200, open(f, "rb").read(), "text/html; charset=utf-8")
        if u.path in ("/nextsteps", "/nextsteps.html"):
            f = os.path.join(HERE, "nextsteps.html")
            if not os.path.exists(f):
                return self._send(404, "Run `python3 ui/build_nextsteps.py` first.", "text/plain")
            return self._send(200, open(f, "rb").read(), "text/html; charset=utf-8")
        if u.path == "/api/nextsteps":
            try:
                import build_nextsteps
                src = os.path.join(ROOT, "tracking", "NEXT_STEPS.md")
                groups, meetings = build_nextsteps.parse(open(src, encoding="utf-8").read())
                return self._send(200, json.dumps({"groups": groups, "meetings": meetings}, ensure_ascii=False))
            except Exception as e:
                return self._send(500, json.dumps({"error": str(e)}))
        if u.path == "/api/ping":
            return self._send(200, json.dumps({"ok": True, "root": ROOT}))
        if u.path == "/api/jobs":
            try:
                return self._send(200, json.dumps(parse_jobs(), ensure_ascii=False))
            except Exception as e:
                return self._send(500, json.dumps({"error": str(e)}))
        if u.path == "/api/inbox":
            try:
                path = os.path.join(ROOT, "tracking", "INBOX.md")
                return self._send(200, json.dumps(parse_inbox(path), ensure_ascii=False))
            except Exception as e:
                return self._send(500, json.dumps({"error": str(e)}))
        if u.path == "/api/applications":
            try:
                pipeline, contacts, drafts = parse_applications()
                return self._send(200, json.dumps(
                    {"pipeline": pipeline, "contacts": contacts, "drafts": drafts}, ensure_ascii=False))
            except Exception as e:
                return self._send(500, json.dumps({"error": str(e)}))
        if u.path == "/api/open":
            return self._open(parse_qs(u.query))
        if u.path == "/api/stream":
            task = (parse_qs(u.query).get("task") or [""])[0]
            return self._stream(task)
        return self._send(404, "not found", "text/plain")

    def do_POST(self):
        u = urlparse(self.path)
        if u.path in ("/api/app-status", "/api/draft-sent", "/api/nextstep-done", "/api/nextstep-reorder"):
            try:
                n = int(self.headers.get("Content-Length", 0) or 0)
                payload = json.loads(self.rfile.read(n) or b"{}")
            except Exception as e:
                return self._send(400, json.dumps({"ok": False, "error": str(e)}))
            if u.path == "/api/app-status":
                return self._app_status(payload)
            if u.path == "/api/nextstep-done":
                return self._nextstep_done(payload)
            if u.path == "/api/nextstep-reorder":
                return self._nextstep_reorder(payload)
            return self._draft_sent(payload)
        return self._send(404, "not found", "text/plain")

    def _nextstep_done(self, payload):
        """Toggle a Next-Steps item's done flag -> tracking/nextsteps_done.json sidecar."""
        iid = str(payload.get("id", "")).strip()
        if not iid:
            return self._send(400, json.dumps({"ok": False, "error": "no id"}))
        path = os.path.join(ROOT, "tracking", "nextsteps_done.json")
        try:
            done = set(json.load(open(path, encoding="utf-8")))
        except Exception:
            done = set()
        now = (iid not in done) if payload.get("value") is None else bool(payload.get("value"))
        done.add(iid) if now else done.discard(iid)
        json.dump(sorted(done), open(path, "w", encoding="utf-8"), ensure_ascii=False)
        return self._send(200, json.dumps({"ok": True, "id": iid, "done": now}))

    def _nextstep_reorder(self, payload):
        """Persist a drag-to-reorder result for one Next-Steps section ->
        tracking/nextsteps_order.json sidecar ({section: [item-id, ...]}).
        A saved order overrides the default due-date sort for that section."""
        section = str(payload.get("section", "")).strip()
        order = payload.get("order")
        if not section or not isinstance(order, list):
            return self._send(400, json.dumps({"ok": False, "error": "need section + order[]"}))
        path = os.path.join(ROOT, "tracking", "nextsteps_order.json")
        try:
            state = json.load(open(path, encoding="utf-8"))
        except Exception:
            state = {}
        state[section] = [str(x) for x in order]
        json.dump(state, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        return self._send(200, json.dumps({"ok": True, "section": section}))

    def _app_status(self, payload):
        """Rewrite the Stage cell of one row in APPLICATIONS.md's Pipeline table.
        Row is located by (company, role) and must match exactly one line."""
        value = payload.get("value")
        if value not in STAGE_OPTS:
            return self._send(400, json.dumps({"ok": False, "error": "bad stage"}))
        company = _clean_md(str(payload.get("company", "")))
        role = _clean_md(str(payload.get("role", "")))
        path = os.path.join(ROOT, "tracking", "APPLICATIONS.md")
        lines = open(path, encoding="utf-8").read().split("\n")
        matches = []
        mode = None
        for i, ln in enumerate(lines):
            if not ln.startswith("|"):
                mode = None if ln.strip() == "" else mode
                continue
            cells = [c.strip() for c in ln.strip().strip("|").split("|")]
            low = " | ".join(c.lower() for c in cells)
            if set("".join(cells)) <= set("-: "):
                continue
            if "next step" in low and "stage" in low:
                mode = "pipe"; continue
            if "handle" in low or (mode is None and "email" in low and "name" in low):
                mode = "contact"; continue
            if mode == "pipe" and len(cells) >= 6 and _clean_md(cells[0]) == company and _clean_md(cells[1]) == role:
                matches.append((i, cells))
        if len(matches) != 1:
            return self._send(409, json.dumps({"ok": False, "error": f"{len(matches)} rows matched — edit APPLICATIONS.md directly"}))
        i, cells = matches[0]
        cells[2] = value
        lines[i] = "| " + " | ".join(cells) + " |"
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        resp = {"ok": True, "value": value}
        if value == "applied":
            moved = self._move_jobs_folder_by_company(company)
            if moved:
                resp["folder"] = moved
        return self._send(200, json.dumps(resp))

    def _move_jobs_folder_by_company(self, company):
        """APPLICATIONS.md has no Folder column — cross-reference JOBS.md by company
        name to find and relocate the matching folder, and keep its Status in sync."""
        path = os.path.join(ROOT, "tracking", "JOBS.md")
        lines = open(path, encoding="utf-8").read().split("\n")
        matches = []
        for i, ln in enumerate(lines):
            if not ln.startswith("|"):
                continue
            cells = [x.strip() for x in ln.strip().strip("|").split("|")]
            if len(cells) < 8 or cells[0] in ("#", "") or set(cells[0]) <= set("-") or cells[1] in ("Company", ""):
                continue
            if cells[1].replace("**", "").strip().lower() == company.lower():
                matches.append((i, cells))
        if len(matches) != 1:
            return None
        i, cells = matches[0]
        m = re.search(r"`([^`]+)`", cells[6])
        if not m:
            return None
        new_rel = _move_to_applied(m.group(1))
        if not new_rel or new_rel == m.group(1):
            return None
        cells[6] = f"`{new_rel}`"
        cells[5] = "**applied**"
        lines[i] = "| " + " | ".join(cells) + " |"
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        return new_rel

    def _draft_sent(self, payload):
        """Delete one '### Company · Contact' block from the Follow-up drafts section
        of APPLICATIONS.md, matched by company + subject. Marking a draft sent removes it."""
        company = _clean_md(str(payload.get("company", ""))).lower()
        subject = _clean_md(str(payload.get("subject", ""))).lower()
        path = os.path.join(ROOT, "tracking", "APPLICATIONS.md")
        txt = open(path, encoding="utf-8").read()
        sec_start = re.search(r"\n## Follow-up drafts\n", txt)
        if not sec_start:
            return self._send(404, json.dumps({"ok": False, "error": "no drafts section"}))
        start = sec_start.end()
        nxt = re.search(r"\n## ", txt[start:])
        end = start + nxt.start() if nxt else len(txt)
        section = txt[start:end]
        target = None
        for b in re.finditer(r"### (.+?)\n(.*?)(?=\n### |\Z)", section, re.S):
            head, blk = b.group(1), b.group(2)
            comp = _clean_md(head.split("·")[0]).lower()
            sm = re.search(r"Subject:\**\s*(.+)", blk)
            subj = _clean_md(sm.group(1)).lower() if sm else ""
            if comp == company and (not subject or subj == subject):
                target = b
                break
        if target is None:
            return self._send(409, json.dumps({"ok": False, "error": "draft not found — edit APPLICATIONS.md directly"}))
        abs_start, abs_end = start + target.start(), start + target.end()
        new_txt = txt[:abs_start] + txt[abs_end:]
        new_txt = re.sub(r"\n{3,}", "\n\n", new_txt)
        with open(path, "w", encoding="utf-8") as f:
            f.write(new_txt)
        return self._send(200, json.dumps({"ok": True}))

    def _open(self, q):
        """Reveal an application folder / open its CV PDF in the OS. Confined to applications/."""
        rel = (q.get("path") or [""])[0]
        what = (q.get("what") or ["folder"])[0]
        apps = os.path.realpath(os.path.join(ROOT, "applications"))
        target = os.path.realpath(os.path.join(ROOT, rel))
        if not (target == apps or target.startswith(apps + os.sep)):
            return self._send(403, json.dumps({"ok": False, "error": "outside applications/"}))
        if not os.path.exists(target):
            return self._send(404, json.dumps({"ok": False, "error": "folder not found"}))
        if what == "cv" and os.path.isdir(target):
            # deliverable is "<Name> - CV.pdf" (any *.pdf that isn't the raw cv.pdf)
            pdfs = [f for f in sorted(os.listdir(target))
                    if f.lower().endswith(".pdf") and f.lower() != "cv.pdf"]
            if pdfs:
                target = os.path.join(target, pdfs[0])
        if sys.platform == "darwin":
            cmd = ["open", target]
        elif sys.platform.startswith("linux"):
            cmd = ["xdg-open", target]
        else:
            cmd = ["explorer", target]
        try:
            subprocess.Popen(cmd)
            return self._send(200, json.dumps({"ok": True, "opened": os.path.basename(target)}))
        except Exception as e:
            return self._send(500, json.dumps({"ok": False, "error": str(e)}))

    def _stream(self, task):
        if task not in TASKS:
            return self._send(400, "unknown task", "text/plain")
        argv, cwd = TASKS[task]
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.end_headers()

        def emit(data, event=None):
            try:
                if event:
                    self.wfile.write(f"event: {event}\n".encode())
                for line in str(data).split("\n"):
                    self.wfile.write(f"data: {line}\n".encode())
                self.wfile.write(b"\n")
                self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                raise

        env = dict(os.environ)
        if task == "mail" and not env.get("EMAIL_PASS"):
            emit("EMAIL_USER / EMAIL_PASS not set — restart serve.py with them exported "
                 "to enable the mail run (Gmail App Password).")
            emit("1", "done")
            return
        try:
            p = subprocess.Popen(argv, cwd=cwd, env=env, stdout=subprocess.PIPE,
                                 stderr=subprocess.STDOUT, bufsize=1, text=True)
            for line in iter(p.stdout.readline, ""):
                emit(line.rstrip("\n"))
            p.stdout.close()
            emit(str(p.wait()), "done")
        except BrokenPipeError:
            pass
        except Exception as e:
            try:
                emit(f"server error: {e}")
                emit("1", "done")
            except Exception:
                pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--no-open", action="store_true")
    args = ap.parse_args()

    # make sure the dashboard + other pages exist / are current. applications.html
    # and nextsteps.html only need their source .md to exist; conversations.html
    # is skipped here if tracking/CONVERSATIONS.md doesn't exist yet (optional page).
    for script, needs in (
        (os.path.join("ui", "build_dashboard.py"), None),
        (os.path.join("ui", "build_applications.py"), "APPLICATIONS.md"),
        (os.path.join("ui", "build_nextsteps.py"), "NEXT_STEPS.md"),
        (os.path.join("ui", "build_conversations.py"), "CONVERSATIONS.md"),
    ):
        if needs and not os.path.exists(os.path.join(ROOT, "tracking", needs)):
            continue
        try:
            subprocess.run(["python3", script], cwd=ROOT, check=False)
        except Exception:
            pass

    url = f"http://localhost:{args.port}"
    srv = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"● Job-search command center → {url}")
    print(f"  serving {ROOT}")
    print(f"  mail run: {'ENABLED' if os.environ.get('EMAIL_PASS') else 'set EMAIL_USER/EMAIL_PASS to enable'}")
    print("  Ctrl-C to stop.")
    if not args.no_open:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped.")


if __name__ == "__main__":
    main()
