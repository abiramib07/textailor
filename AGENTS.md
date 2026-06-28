# TexTailor — Agent Inventory & AI Architecture Audit

---

## 1. Agent Count

TexTailor has **6 agents** in `src/agents/`, plus **2 AI-powered utilities** outside that folder.

| # | Name | File | AI? | Type |
|---|---|---|---|---|
| 1 | Recruiter Agent | `agents/recruiter.py` | Claude | Single-shot analyst |
| 2 | Rewriter Agent | `agents/rewriter.py` | Claude | Single-shot transformer |
| 3 | ATS Scorer | `agents/ats_scorer.py` | No (regex) | Deterministic scorer |
| 4 | Chat Editor | `agents/chat_editor.py` | Claude | Two-phase planner + executor |
| 5 | Editor Agent | `agents/editor.py` | Claude | Single-shot + optional clarification loop |
| 6 | Diagnoser | `agents/diagnoser.py` | Stub | Not yet implemented |
| — | MD Converter | `src/md_converter.py` | Claude | Single-shot converter (not in agents/) |
| — | Claude Client | `src/claude_client.py` | — | Shared transport layer (subprocess) |

**Claude-powered: 5 active agents + 1 utility**  
**Subagents: 0** (no agent spawns or calls another agent)

---

## 2. What Each Agent Actually Does

### Recruiter Agent
- **Input:** raw JD text + plain-text resume  
- **One call to Claude:** keyword gap analysis  
- **Output:** structured JSON — `required_keywords`, `missing_from_resume`, `priority_adds`, `key_action_verbs`  
- **Pattern:** Single-shot prompt → JSON parse

### Rewriter Agent
- **Input:** resume sections dict + priority keywords + action verbs from Recruiter  
- **One call to Claude:** rewrite all sections simultaneously in one prompt  
- **Output:** dict of `{section_name: rewritten_latex}`  
- **Safety:** `_escape_ampersands()` post-processes output to catch unescaped `&`  
- **Pattern:** Single-shot prompt → marker-delimited section extraction

### ATS Scorer
- **No AI involved** — pure regex keyword matching against the rewritten plain text  
- **Formula:** `overall = required_score × 0.8 + preferred_score × 0.2`  
- **Output:** score %, found/missing keyword lists, `%NEEDS_METRIC` count  
- **Pattern:** Deterministic function

### Chat Editor Agent
- **Two separate Claude calls:**
  - `plan()` — reads message + full `main.tex`, returns plain-English plan + changes list. **Zero file writes.**
  - `execute()` — given the confirmed plan, generates exact LaTeX patches, validates every `old` string exists, backs up, applies, compiles. Auto-reverts if compilation fails.
  - `undo()` — no Claude call; restores `inputs/backups/vN.tex` and recompiles.
- **Pattern:** Plan → Human confirm → Execute (closest to agentic loop in the codebase)

### Editor Agent (Pending Edits)
- **Input:** raw content from `inputs/pending-edits.md` + full `main.tex`  
- **First Claude call:** analyse edit type, generate LaTeX block, identify insertion point  
- **Optional second Claude call:** if `ambiguities` are returned, answers are appended and Claude is re-called  
- **Human confirm:** terminal Y/n before any write  
- **Pattern:** Single-shot with optional one-level retry loop

### MD Converter (utility)
- `tex_to_md()` — one Claude call: converts full LaTeX body to Markdown  
- `md_to_tex()` — one Claude call: converts Markdown back to LaTeX body (preamble stitched back separately)  
- **Pattern:** Single-shot prompt → text response

---

## 3. How AI Orchestration Works Today

The orchestration is **hardcoded and sequential** — no dynamic routing, no agent-to-agent calls.

```
Pipeline (api.py / main.py)   ← acts as the orchestrator
    │
    ├─ parse_resume()          (no AI)
    │       ↓ sections dict
    ├─ recruiter.analyze()     (Claude call 1)
    │       ↓ keyword gap result
    ├─ rewriter.rewrite()      (Claude call 2)
    │       ↓ rewritten sections
    ├─ latex_patcher + compile (no AI)
    │       ↓ PDF path
    └─ ats_scorer.score()      (no AI)
```

**Information flows only forward.** The ATS Scorer's result is never fed back to the Rewriter automatically — it requires a manual user click on "Boost to 90%+" to trigger a second rewrite pass.

### Chat Editor — the only loop

```
User message
    → plan()      [Claude: describe changes only]
    → UI shows plan
    → User: "Yes, apply"
    → execute()   [Claude: generate patches]
    → compile
    → auto-revert if compile fails
```

This is the only place in the codebase where there is **observe → reason → act** structure, though it's one iteration deep (no re-planning on failure).

### Pending Edits — optional one-level loop

```
pending-edits.md content
    → analyse()   [Claude call 1]
    → if ambiguities → ask user → analyse() [Claude call 2]
    → terminal confirm
    → patch + archive
```

---

## 4. Are We at Industry Standard?

### What we're doing right

| Practice | Status |
|---|---|
| Single responsibility per agent | Each agent has exactly one job |
| Structured output (JSON) | All AI agents return parseable JSON |
| Human-in-the-loop for destructive ops | Chat editor and pending-edits require explicit confirmation |
| Auto-revert on failure | Chat edit, MD sync both restore backup if pdflatex fails |
| Separation of planning and execution | Chat editor's `plan()` / `execute()` split is the correct pattern |
| Prompt engineering | Google XYZ formula, LaTeX escaping rules, output markers |
| Safety post-processing | `_escape_ampersands()` catches what the model misses |

### What's missing vs. current AI-agent standards

**1. No ReAct loop (Reason + Act + Observe)**  
The rewriter sends one prompt and accepts whatever comes back. It does not look at the output, check if the LaTeX is valid, and re-try. A standard agentic rewriter would:
- Generate the rewrite
- Run pdflatex on it
- If it fails → read the error → fix → try again (up to N times)

**2. No agent-to-agent communication**  
Every agent is called directly by the pipeline (`api.py`/`main.py`). There is no orchestrator agent that decides *which* agent to call next based on state. The sequence is always the same 5 steps.

**3. No shared context / memory between agents**  
Information passes through Python function arguments. The Recruiter result is manually passed as a parameter to the Rewriter. There is no shared memory store (vector DB, key-value store) that any agent can read from or write to.

**4. ATS feedback loop is not automatic**  
The ATS Scorer runs, gets a score, and the result sits in a dict. Only if the user manually clicks "Boost" does the system re-run the Rewriter with the missing keywords. A true agentic system would close this loop automatically: if `score < 90`, feed `required_missing` back to the Rewriter, re-score, repeat until threshold is hit or max iterations reached.

**5. No tool use / function calling**  
Agents do not have access to tools (search, file read, shell exec) declared in the Claude prompt. They all work purely through natural language → JSON. Claude's native tool-use feature (declaring tools in the API call) is not used.

**6. No retry with self-reflection**  
If Claude returns invalid JSON, the agent raises an error or returns a default. No agent says "I got back X, it failed for reason Y, let me retry with a corrected prompt."

**7. No streaming**  
All Claude calls are synchronous `subprocess.run()` — the user sees nothing until the full response is ready. Streaming would allow real-time token display in the chat panel.

**8. Diagnoser is a stub**  
`agents/diagnoser.py` has one comment line. It was meant to parse pdflatex error logs and explain them. It would be the natural tool to give to the rewriter's self-correction loop.

---

## 5. What "Standard" Looks Like vs. What We Have

```
STANDARD AGENTIC SYSTEM                    TEXTAILOR TODAY
────────────────────────────               ─────────────────────────────
Orchestrator agent                         Hardcoded pipeline in api.py
  decides which agents to call
  based on state

Agents with tool use                       Agents with only prompts
  (search, run_code, read_file)            (natural language → JSON)

ReAct loop per agent                       Single-shot per agent
  reason → act → observe → repeat         (except chat editor: 2 phases)

Shared memory / context store              Function-argument passing only
  agents read/write a shared state

Automatic feedback loops                   Manual user-triggered loops
  ATS < 90 → auto re-rewrite              (Boost button)

Parallel agent execution                   Sequential only
  recruiter + parser run simultaneously

Self-correction on tool failure            Hard fail on bad JSON
  retry with error context
```

---

## 6. Concrete Upgrades (priority order)

**High impact, low effort**

1. **Auto-boost loop** — in the pipeline, after scoring, if `overall_score < config["target_ats_score"]`, automatically re-run the Rewriter with `required_missing` as priority keywords. Cap at 2 iterations. Remove the need for the manual Boost button.

2. **Retry on bad JSON** — wrap every `json.loads()` in all agents with a retry: if parsing fails, send Claude back the raw output + `"The above was not valid JSON. Return only the JSON object:"` and try once more.

3. **Implement Diagnoser** — `agents/diagnoser.py` reads the pdflatex `.log`, extracts the error, sends it to Claude with the current `.tex`, and returns a one-sentence human-readable explanation + the exact fix. Used by the Chat Editor's `execute()` when compilation fails.

**Medium impact, medium effort**

4. **ReAct in Chat Editor** — after `execute()` applies patches and compilation fails, instead of just reverting, pass the error log to Claude along with the patches and let it re-try with corrected LaTeX (up to 2 retries before reverting).

5. **Streaming Claude responses** — switch `claude_client.py` to stream stdout line-by-line and send server-sent events (SSE) from FastAPI. The chat panel would show Claude thinking in real time.

**Lower priority / architectural**

6. **Dynamic orchestration** — replace the hardcoded pipeline sequence in `api.py` with a simple state machine or task graph. The orchestrator reads the current state and decides the next step, making it easier to add new steps (e.g., a "style check" agent) without touching pipeline code.

7. **Tool use for Recruiter** — declare file-read and web-search as tools in the Recruiter prompt so it can optionally look up the company for seniority context.
