# Database Recommendation — Phase 2

## Recommendation: keep SQLite, add file storage for attachments

Continue what's already working (`src/auth/data/auth.db`, `src/history.py`'s
`history.db`) rather than introducing a new database technology. One SQLite
file per domain, plus a plain filesystem folder for binary attachments
(screenshots), with SQLite holding the file paths — the same pattern
`history.py` already uses for PDFs (`pdf_path` column pointing at a file on
disk, not the PDF stored as a blob).

## Why not Postgres / MongoDB / cloud DB

This app has no server to run one on — it's a local-first tool that shells
out to the Claude Code CLI on your own machine, with no API key and no
cloud dependency anywhere else in the stack. Adding Postgres would mean:
running and keeping alive a separate database server process, a connection
string to manage, a backup story you don't currently need, and a new
failure mode ("is Postgres running?") for a single-user local tool. None of
Phase 2's data volume or access pattern needs it:

- Single user, single machine, no concurrent writers.
- Total data size (years of JDs, interview notes, a few thousand emails) is
  low tens of MB — SQLite handles that trivially.
- Full-text search over JD history / topic mapping is covered by SQLite's
  built-in **FTS5** extension — no need for Elasticsearch.

**Reconsider this if:** you ever want multi-device sync without going
through a manual export, or a second person uses the tool. Neither is true
today.

## Proposed schema additions

One new SQLite file, `src/career/data/career.db` (new `src/career/` module,
mirroring `src/auth/`), covering Phase 2's structured data. Screenshots go
on disk under `src/career/data/attachments/<post_id>/`.

```sql
-- LinkedIn / job post archive (item 1)
CREATE TABLE job_posts (
    id            TEXT PRIMARY KEY,
    url           TEXT,                 -- nullable: post may only exist as a screenshot
    company_name  TEXT,
    role_title    TEXT,
    raw_text      TEXT,                 -- pasted post text, if any
    created_at    REAL NOT NULL
);

CREATE TABLE job_post_attachments (
    id            TEXT PRIMARY KEY,
    job_post_id   TEXT NOT NULL REFERENCES job_posts(id),
    file_path     TEXT NOT NULL,        -- e.g. src/career/data/attachments/<post_id>/1.png
    created_at    REAL NOT NULL
);

-- Email generator learning set (item 2)
CREATE TABLE email_examples (
    id            TEXT PRIMARY KEY,
    job_post_id   TEXT REFERENCES job_posts(id),
    subject       TEXT NOT NULL,
    body          TEXT NOT NULL,
    approved_at   REAL NOT NULL         -- only emails you actually approved/sent go here
);

-- JD topic mapping (item: "topic mapping" tab)
CREATE TABLE jd_keyword_observations (
    id            TEXT PRIMARY KEY,
    job_post_id   TEXT REFERENCES job_posts(id),
    keyword       TEXT NOT NULL,
    category      TEXT,                 -- "required" | "preferred"
    years_bucket  TEXT,                 -- e.g. "0-2", "3-5", "5+", parsed from the JD
    observed_at   REAL NOT NULL
);
CREATE INDEX idx_keyword_lookup ON jd_keyword_observations(keyword, years_bucket);

-- Interview prep checklist (item: checklist tab)
CREATE TABLE interview_topics (
    id            TEXT PRIMARY KEY,
    company_name  TEXT NOT NULL,
    topic         TEXT NOT NULL,
    covered       INTEGER NOT NULL DEFAULT 0,
    github_url    TEXT,
    youtube_url   TEXT,
    notes         TEXT,
    created_at    REAL NOT NULL
);

-- Personal info clipboard (item 4a)
CREATE TABLE personal_info (
    key           TEXT PRIMARY KEY,     -- "linkedin_url", "email", "short_pitch", ...
    value         TEXT NOT NULL,
    updated_at    REAL NOT NULL
);

-- Apply-later queue (item 4b)
CREATE TABLE apply_later (
    id            TEXT PRIMARY KEY,
    url           TEXT NOT NULL,
    company_name  TEXT,
    notes         TEXT,
    applied       INTEGER NOT NULL DEFAULT 0,
    created_at    REAL NOT NULL
);
```

## Screenshot storage specifics

- Paste-to-save: the browser Clipboard API (`navigator.clipboard.read()`)
  can read an image directly off the clipboard in a paste event — no need
  to save-to-disk-then-upload manually. Backend receives it as a multipart
  file upload, writes it to `attachments/<post_id>/`, and rejects anything
  that isn't an image (mimetype check) — first real file-upload surface
  in this app, worth a size cap (e.g. 10 MB) since it's a local tool with
  no storage quota otherwise.
- Multiple screenshots per post: `job_post_attachments` is already
  one-to-many.

## Full-text search (for the JD/topic-mapping "search all pasted data" ask)

SQLite FTS5 gives you `SELECT * FROM job_posts_fts WHERE job_posts_fts MATCH 'kubernetes'`
style search over `raw_text` essentially for free — no separate search
engine needed. Worth wiring up once the topic-mapping tab has real data in
it.
