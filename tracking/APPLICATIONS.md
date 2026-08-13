# Applications — live pipeline

_Last updated: (new)_

The action-oriented view of what's actually in flight — stage, who to talk to,
last contact, and the **next step**. (`JOBS.md` is the broad tracker of every
posting; this is only the roles with a real application or conversation.)

> **Stages:** `applied` (submitted, awaiting) → `interviewing` → `offer` → `accepted` / `rejected` / `withdrawn`
> The UI **Applications** page is generated from the pipeline table below
> (`python3 ui/build_applications.py`, or served live at `/applications.html`).
> It's also auto-merged with every `JOBS.md` row whose Status is in that same
> family, so this table only needs to add contact/next-step detail — it doesn't
> have to duplicate every applied row by hand.

## Pipeline

| Company | Role | Stage | Contact | Last email | Next step |
|---------|------|-------|---------|------------|-----------|
| _(example — delete)_ Acme | ML Engineer | applied | Jane Doe (recruiter) | 2026-01-01 · application ack | Await; follow up in ~1 week if quiet |

## Contacts

| Name | Company | Role | Email | Notes |
|------|---------|------|-------|-------|
| _(example — delete)_ Jane Doe | Acme | Recruiter | jane@acme.example | Sourced the role, responsive |

## Follow-up drafts

_(none pending)_

Add ready-to-send email drafts here, one per heading shaped like
"h3 Company [middle dot] Contact", with a "- To:" line, a "- Subject:" line,
then the body as plain paragraphs below. See `ui/build_applications.py`'s
`parse_drafts()` for the exact fields it reads. The Applications UI lists
these under "Ready to send" and lets you copy/open in your mail client, or
mark sent (which deletes the heading's block). The parser is regex-based on
raw Markdown headings, so avoid writing an example of the heading shape in
prose here — it will be picked up as a real draft.
