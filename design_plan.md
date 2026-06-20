# AI Resume Automater — Design Plan

> Knowledge source: `prompt.md.txt` (the 4-skill pipeline: Diagnoser → Recruiter → Rewriter → Hiring Manager)
> Goal: Fully automate that 4-step manual Claude chat into a single script that runs end-to-end.

---

## What We're Automating

Your `prompt.md.txt` defines a 4-prompt chain that a person runs manually in a Claude chat.
This tool removes the human from that loop entirely:

```
Manual today:
  You → paste resume → paste JD → run 4 prompts → copy output → paste into Overleaf → compile

Automated goal:
  You → paste JD into jd_input.txt → wait 60 seconds → get tailored PDF
```

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     TRIGGER LAYER                           │
│  watchdog watches jd_input.txt for changes                  │
└────────────────────────┬────────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────────┐
│                   PIPELINE (4 agents, sequential)           │
│                                                             │
│  Agent 1 — DIAGNOSER                                        │
│    Input : master resume .tex (converted to plain text)     │
│    Task  : find ATS red flags in structure/formatting       │
│    Output: list of structural fixes needed                  │
│                         │                                   │
│  Agent 2 — RECRUITER                                        │
│    Input : JD text + master resume text                     │
│    Task  : extract JD keywords, find gaps in resume         │
│    Output: ranked keyword list (missing vs present)         │
│                         │                                   │
│  Agent 3 — REWRITER                                         │
│    Input : master .tex + keyword gaps from Agent 2          │
│    Task  : rewrite bullets using Google XYZ formula +       │
│            weave in missing keywords naturally              │
│    Output: new LaTeX content for each section               │
│                         │                                   │
│  Agent 4 — ATS SCORER                                       │
│    Input : rewritten resume text + JD keywords              │
│    Task  : calculate match %, flag anything still missing   │
│    Output: ats_report.txt                                   │
│                                                             │
└────────────────────────┬────────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────────┐
│                   OUTPUT LAYER                              │
│  LaTeX Patcher  → writes resume_tailored.tex                │
│  Compiler       → pdflatex → resume_tailored.pdf            │
│  Notifier       → Windows toast + open output folder        │
└─────────────────────────────────────────────────────────────┘
```

---

## Folder Structure

```
D:\AI resume automater\
│
├── prompt.md.txt              ← your original 4-skill prompt guide (knowledge base)
├── design_plan.md             ← this file
├── jd_input.txt               ← PASTE JD HERE to trigger the pipeline
│
├── resume\
│   └── main.tex               ← your Overleaf master resume (never auto-modified)
│
├── output\
│   └── [JobTitle]_[YYYY-MM-DD]\
│       ├── resume_tailored.tex
│       ├── resume_tailored.pdf
│       └── ats_report.txt
│
├── src\
│   ├── main.py                ← entry point + file watcher
│   ├── agents\
│   │   ├── diagnoser.py       ← Agent 1 prompt + Claude API call
│   │   ├── recruiter.py       ← Agent 2 prompt + Claude API call
│   │   ├── rewriter.py        ← Agent 3 prompt + Claude API call
│   │   └── ats_scorer.py      ← Agent 4 scoring logic
│   ├── latex_parser.py        ← reads .tex, extracts section text
│   ├── latex_patcher.py       ← writes AI output back into .tex safely
│   ├── compiler.py            ← runs pdflatex, captures errors
│   └── notifier.py            ← Windows toast notification
│
├── config.json                ← paths, preferences, model choice
├── .env                       ← ANTHROPIC_API_KEY (never committed)
└── requirements.txt
```

---

## Agent Prompts (Derived from prompt.md.txt)

### Agent 1 — Diagnoser
Adapted from the "read it like the software does" prompt.

```
System: You are an ATS resume parser analyzing a LaTeX resume.
        The resume will be provided as plain text extracted from .tex source.

Task:
1. Flag anything that could break ATS parsing: multi-column layouts, tables,
   unusual section names, special characters, text boxes.
2. List every section an ATS might misread, and why.
3. Output a JSON list of { "issue": "...", "fix": "...", "severity": "high|medium|low" }

Resume text:
{resume_plain_text}
```

### Agent 2 — Recruiter
Adapted from the "find the keywords you're missing" prompt.

```
System: You are a senior recruiter doing keyword gap analysis.

Task:
1. Extract all skills, tools, and keywords from the job description below.
   Separate into: required vs preferred.
2. Check which of these appear in the resume (exact or close match).
3. Output JSON:
   {
     "job_title": "...",
     "required_keywords": ["..."],
     "preferred_keywords": ["..."],
     "present_in_resume": ["..."],
     "missing_from_resume": ["..."],
     "priority_adds": ["top 10 missing, ranked by importance"]
   }

Job Description:
{jd_text}

Resume:
{resume_plain_text}
```

### Agent 3 — Rewriter
Adapted from the "rebuild every bullet with Google XYZ formula" prompt.

```
System: You are an expert resume writer. You will rewrite LaTeX resume sections.
        Output must be valid LaTeX that compiles without errors.
        Preserve all custom commands, environments, and macros from the original.

Rules:
- Rewrite bullets using: "Accomplished [X], as measured by [Y], by doing [Z]"
- Weave in these missing keywords naturally (no stuffing): {priority_keywords}
- Keep only truthful content — do not invent metrics or experience
- If a bullet has no quantifiable result, improve the language but flag it
- Output only the modified LaTeX for these sections: Experience, Skills, Projects
- Do not touch: Education, Certifications, Contact Info

Original LaTeX sections:
{latex_sections}

Missing keywords to incorporate:
{priority_keywords}
```

### Agent 4 — ATS Scorer
Logic-based scoring (no Claude needed for this one — computed locally).

```
Score = (keywords_found_in_tailored_resume / total_required_keywords) * 100

Report includes:
- Overall match %
- Required keywords: found vs missing
- Preferred keywords: found vs missing
- Bullets that still lack quantification (flagged by Agent 3)
- Recommendation: "Ready to submit" or "Review these gaps: ..."
```

---

## LaTeX Handling Strategy

This is the most delicate part. Your `.tex` has custom commands and structure.

### Confirmed Section Names (from main.tex)
Your template uses `\header{}` not `\section{}` — the parser must match this.

```
\header{Career Objective}   ← rewrite the paragraph text only
\header{Experience}         ← rewrite \item[] bullet blocks
\header{Projects}           ← rewrite \item[] bullet blocks
\header{Skills}             ← rewrite \item entries under each \textbf{category}
\header{Education}          ← DO NOT TOUCH (factual)
```

### Confirmed Custom Commands (must be preserved, never rewritten)
```latex
\header{}         — section title with rule underline
\employer{}{}{}   — company/date/role block
\area{}{}         — sub-area label
\schoolwithcourses{}{}{}{} — education block
\lineunder        — horizontal rule
```
The AI will only rewrite content *between* these commands, never the commands themselves.

### Step 1 — Parse sections safely
Use regex to locate section boundaries by matching `\header{Name}` markers:
```python
# Pattern: r'\\header\{(Career Objective|Experience|Projects|Skills)\}(.*?)(?=\\header\{|\\end\{document\})'
# flags: re.DOTALL
# Extract the raw LaTeX block between headers
# Send to Agent 3 as-is (preserves \item[], \textbf{}, \hfill etc.)
```

### Step 2 — Replace sections safely
Agent 3 returns modified LaTeX for each section.
Patcher does a block-level replace (not line-by-line) to avoid partial corruption.

### Step 3 — Compile and catch errors
Run `pdflatex -interaction=nonstopmode resume_tailored.tex`
If it fails, save the error log alongside the .tex so you can debug.
On success, open the output folder.

---

## Tech Stack

| Component | Tool | Reason |
|-----------|------|--------|
| Language | Python 3.14 | Confirmed installed |
| AI | Claude Code CLI (`claude -p`) | Uses existing Pro subscription — no API key needed |
| File watcher | `watchdog` | Detects jd_input.txt save event |
| LaTeX compiler | MiKTeX (Windows) | CLI: `pdflatex`, auto package install — confirmed choice |
| Notifications | `plyer` | Windows toast popup |
| Output format | Structured JSON between agents | Clean handoffs, easy to debug |

### How AI calls work (no API key required)

```python
import subprocess, json

def call_claude(prompt: str) -> str:
    result = subprocess.run(
        ['claude', '-p', prompt, '--output-format', 'text'],
        capture_output=True, text=True, encoding='utf-8'
    )
    return result.stdout.strip()
```

Every agent (Diagnoser, Recruiter, Rewriter, Scorer) calls this function.
Claude Code uses the logged-in Pro subscription — same session you're in right now.

### No .env file needed
No `ANTHROPIC_API_KEY`. No `python-dotenv`. Subscription auth is handled by Claude Code itself.

---

## config.json Schema

```json
{
  "resume_path": "D:\\AI resume automater\\resume\\main.tex",
  "jd_input_path": "D:\\AI resume automater\\jd_input.txt",
  "output_dir": "D:\\AI resume automater\\output",
  "auto_open_output": true,
  "target_ats_score": 95,
  "latex_compiler": "pdflatex",
  "sections_to_rewrite": ["Career Objective", "Experience", "Projects", "Skills"]
}
```

---

## Trigger Flow (End-to-End)

```
1. You copy a job description from LinkedIn / company site
2. Paste it into:  D:\AI resume automater\jd_input.txt  and save

3. watchdog fires → main.py starts pipeline

4. latex_parser.py reads main.tex
   → extracts plain text (for Agents 1 & 2)
   → extracts section LaTeX blocks (for Agent 3)

5. Agent 1 (Diagnoser) → structural ATS issues flagged (logged, not blocking)

6. Agent 2 (Recruiter) → keyword gap JSON produced

7. Agent 3 (Rewriter) → modified LaTeX sections produced

8. latex_patcher.py → writes resume_tailored.tex (copy of main.tex with new sections)

9. compiler.py → runs pdflatex → resume_tailored.pdf

10. Agent 4 (Scorer) → computes ATS % → writes ats_report.txt

11. notifier.py → Windows toast:
    "Resume ready — 96% ATS match  |  Output: SeniorMLEngineer_2026-06-20"

12. Output folder auto-opens in Explorer
```

---

## Build Phases

| Phase | Deliverable | What you can test |
|-------|------------|-------------------|
| 1 | `latex_parser.py` working | Print extracted sections to console |
| 2 | Agent 2 (Recruiter) working | Paste JD + resume → get keyword JSON |
| 3 | Agent 3 (Rewriter) working | Get back valid LaTeX bullets |
| 4 | `latex_patcher.py` working | See modified .tex file produced |
| 5 | `compiler.py` working | Get a compiled PDF |
| 6 | Agent 1 + Agent 4 wired in | Full pipeline, ATS report generated |
| 7 | `watchdog` file watcher | Drop JD → everything runs hands-free |
| 8 | Windows toast notification | True zero-touch experience |

---

## Guardrails Built Into Agent Prompts

- Agent 3 is explicitly told: **do not invent metrics** — matches your `prompt.md.txt` warning
- Agent 3 flags bullets without numbers rather than fabricating them
- Master `main.tex` is never written to — all output goes to `/output/[job]/`
- If `pdflatex` fails, error log is saved and you're notified — no silent failures
- Agent 2 separates "skills you have but didn't mention" from "skills you don't have"

---

## Open Questions Before Building

| # | Question | Status |
|---|----------|--------|
| 1 | Path to `main.tex` | RESOLVED — `D:\AI resume automater\resume\main.tex` |
| 2 | Section command | RESOLVED — uses `\header{}` not `\section{}` |
| 3 | Sections to rewrite | RESOLVED — Career Objective, Experience, Projects, Skills |
| 4 | Sections to lock | RESOLVED — Education (factual, never touched) |
| 5 | LaTeX distribution | RESOLVED — MiKTeX (install from miktex.org before running) |
| 6 | Overleaf sync | RESOLVED — not needed, local copy maintained manually |
| 7 | Python version | RESOLVED — Python 3.14 |
| 8 | AI auth | RESOLVED — Claude Code CLI (`claude -p`), uses existing Pro subscription |

---

## What Makes This Different from Just Running the Prompts Manually

| Manual chat | This tool |
|-------------|-----------|
| 4 separate copy-paste sessions | One file save |
| You carry context between prompts | JSON handoffs carry it automatically |
| Output is chat text — you re-format it | Output is a ready-to-submit PDF |
| 20-30 minutes per application | ~60 seconds per application |
| Easy to forget ATS rules | Rules are baked into every agent prompt |
| You decide what keywords to add | Recruiter agent ranks and prioritizes |
