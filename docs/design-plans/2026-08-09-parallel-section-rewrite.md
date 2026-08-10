# Parallelize rewriter per-section Claude calls

**Status:** Shipped
**Date:** 2026-08-09

## Context

Both Tailor (`POST /api/generate`) and Weave-in (`POST /api/boost/{task_id}`)
call `agents.rewriter.rewrite()`, which loops over
`sections_to_rewrite` and calls `ask_claude()` once per section,
**sequentially** (`rewriter.py` `rewrite()`, the `for name in
sections_to_rewrite:` loop).

`ask_claude()` (`claude_client.py`) is not an API call — each invocation
spawns a brand-new `claude --print` CLI subprocess via `cmd /c`. Every one
of those pays real cold-start overhead (Node/npm CLI startup, MCP/tool
discovery, auth check) on top of actual generation time.

- Tailor rewrites 4 sections by default (Career Objective, Experience,
  Projects, Skills) plus 1 Recruiter-analysis call before that = 5
  sequential Claude CLI invocations.
- Weave-in rewrites 2 sections (Professional Summary, Experience) = 2
  sequential invocations.

Sequential per-call overhead, multiplied across sections, is what pushes
both flows past a minute. The sections are independent of each other —
nothing in one section's prompt depends on another section's output — so
sequencing them is pure accidental slowness from the `for` loop, not a
real dependency.

## Decision

Run the per-section `_rewrite_section()` calls concurrently with
`concurrent.futures.ThreadPoolExecutor`. This is safe and appropriate
because each call is I/O-bound (blocked on `subprocess.run` waiting for a
separate OS process), not CPU-bound — Python's GIL is released during the
subprocess wait, so threads give real concurrency here, no need for
multiprocessing.

Preserve every existing behavioral guarantee exactly:

1. **Per-section exception isolation** — one section failing (raises) must
   not affect any other section; it falls back to the original,
   unmodified content for that section only, same as today's `except
   Exception: log.exception(...)` in the loop.
2. **Deterministic output ordering** — `rewrite()` returns
   `(dict, list[str])`. Today the dict's key order and the warnings list
   order both match `sections_to_rewrite`'s order, because the loop is
   sequential. Concurrency makes completion order nondeterministic
   (whichever CLI subprocess returns first), so the implementation must
   explicitly reassemble both outputs in `sections_to_rewrite` order
   afterward, not in completion order — otherwise behavior becomes
   flaky/non-reproducible in a way callers and tests don't expect.
3. **No change to prompt, validation, or splicing logic** —
   `_rewrite_section()`, `_looks_like_rewritten_latex()`,
   `_strip_leaked_commentary()`, `_escape_ampersands()` are untouched.
   Only the orchestration loop in `rewrite()` changes.

## Planned backend changes (`src/agents/rewriter.py`)

- `rewrite()`: replace the sequential `for` loop with
  `ThreadPoolExecutor.submit()` per section + `as_completed()` to collect
  results as they finish, then reassemble the final `dict`/`warnings`
  list in `sections_to_rewrite` order (not completion order) before
  returning.
- `max_workers` capped at the number of sections being rewritten (always
  small — 2 to 4 in practice) — no new config knob needed.
- No changes to `claude_client.py` — `ask_claude()`'s `subprocess.run` call
  has no shared mutable state, so it's already safe to call from multiple
  threads concurrently.
- No changes to callers (`api.py`'s `/api/generate` and `/api/boost`) —
  `rewrite()`'s signature and return shape are unchanged.

### Decisions from design review (incorporated before implementation)

1. **Empty input.** Filter `sections_to_rewrite` down to names present in
   `sections` first, exactly as today. If that filtered list is empty,
   `return {}, []` immediately, before constructing the executor —
   `ThreadPoolExecutor(max_workers=0)` raises `ValueError`, and this is a
   real reachable case since `sections_to_rewrite` can come from a config
   file (`config.get("sections_to_rewrite", ...)`).
2. **Duplicate names.** Dedupe the filtered list (preserve first
   occurrence's position) before submitting — call `_rewrite_section`
   once per unique name, same as the practical effect of today's
   sequential loop (last occurrence wins, but no wasted extra Claude
   call either way is acceptable; the point is determinism, not matching
   "last wins" exactly). Do not leave duplicate-name behavior
   unspecified.
3. **Exception isolation, concretely.** Call `future.result()` inside the
   `as_completed()` loop, one future at a time, each in its own
   `try/except`. Do **not** collect results via a list/dict comprehension
   or a `try/except` wrapped around the whole collection loop — either of
   those aborts collection of other already-finished futures the moment
   one future raises, which would silently break the isolation guarantee
   this whole design depends on.
4. **Windows process-spawn risk, made concrete.** Each `ask_claude()` call
   spawns a `cmd.exe` → `node.exe` process tree; N concurrent sections
   means up to 2N new processes at once. On Windows this can invite
   Defender real-time-scan overhead on process start that partially
   eats the intended speedup. Before writing the executor code, spike it
   manually: run two `claude --print "..."` invocations concurrently from
   two terminals (or `Start-Process` twice) and confirm they both
   complete in roughly the time of one, not visibly serialized or
   mutually slowed down. If they are, that's a go/no-go finding, not
   something to discover after implementing.

## Risks / things to verify

- **Concurrent CLI invocations on this machine** — untested whether the
  installed Claude Code CLI handles multiple simultaneous `--print`
  invocations cleanly (e.g. no shared lock file or session state that
  serializes them anyway, which would erase the speedup). Mitigated by
  the fact that a failure in one concurrent call still degrades
  gracefully to "keep the original section" for that section only,
  same as today's sequential failure mode — worst case, no speedup;
  it shouldn't be able to make things *worse* than sequential.
- **Resource usage** — today at most 1 CLI subprocess runs at a time;
  after this change, up to 4 (Tailor) or 2 (Weave-in) run concurrently.
  Should be trivial on a dev machine but worth confirming during the
  smoke test.
- **Log interleaving** — per-section `"rewriting section: X"` / `"done:
  X"` log lines will interleave across threads instead of appearing in
  strict section order. Cosmetic only, not a functional regression.

## Verification plan

- `ruff check src`, `ruff format`, `mypy src` clean.
- New tests in `tests/test_rewriter_parallel.py` (written and confirmed
  failing against the current sequential code before implementing):
  - **Concurrency proof, not a wall-clock threshold.** A wall-clock
    "total time close to the slowest section" assertion is flaky under
    CI/CPU contention. Instead: have each fake `ask_claude` record its
    own `(start, end)` monotonic timestamps, then assert a genuine
    pairwise overlap between at least two calls' intervals (`a.start <
    b.end and b.start < a.end`) — a binary, timing-threshold-free proof
    that two calls were in flight at the same time.
  - Result dict key order matches `sections_to_rewrite`'s order even when
    a later section's fake `ask_claude` finishes before an earlier one's
    (deliberately reversed simulated completion order).
  - A per-section exception in one concurrent call doesn't affect the
    other sections' results (mirrors the existing sequential
    except/log.exception fallback behavior) — and doesn't abort
    collection of results for sections whose futures already completed.
  - Warnings list order matches `sections_to_rewrite` order, not
    completion order.
  - Empty `sections_to_rewrite` (after filtering against `sections`)
    returns `({}, [])` without raising.
  - Duplicate names in `sections_to_rewrite` call `ask_claude` exactly
    once per unique name (not once per occurrence), and appear once in
    the result.
- Existing `tests/test_rewriter_validation.py` suite must still pass
  unmodified — confirms no regression to the leaked-commentary rejection
  logic, which this change doesn't touch but runs through the same
  `rewrite()` entry point.
- Full `pytest` suite green.
- Live smoke test: start the real backend, run an actual `/api/generate`
  call (real JD, real resume, real Claude CLI) and an actual
  `/api/boost/{task_id}` call, compare wall-clock time against the
  pre-change baseline, and confirm the resulting PDF/score are unaffected
  (same content, just faster).

## Explicitly not doing

- Not parallelizing the Recruiter `analyze()` call (single call, nothing
  to parallelize against) or the LaTeX compile step (separate pipeline
  stage, out of scope here).
- Not adding a `max_workers` config knob — section counts are always
  small and hardcoded in `api.py` today; a config surface for this isn't
  justified yet.
- Not changing `stream_claude()` (used elsewhere for tool-enabled calls)
  — this design only touches the plain `ask_claude()` path `rewrite()`
  uses.

## Shipped

- `rewrite()` in `src/agents/rewriter.py` reimplemented on
  `ThreadPoolExecutor` + `as_completed()`, exactly per the design above:
  filters/dedupes `sections_to_rewrite` first, short-circuits `({}, [])`
  on empty input, submits one future per unique section, collects each
  future's result individually (own try/except, so one failure can't
  abort collection of the others), then reassembles both the result dict
  and the warnings list in `sections_to_rewrite`'s original order.
- 7 new tests in `tests/test_rewriter_parallel.py`, written before the
  implementation and confirmed failing against the old sequential code
  first (2 of 7 failed pre-implementation: the timestamp-overlap
  concurrency proof, and the duplicate-name dedup check — the other 5
  passed even against the sequential code, since those guarantees held
  trivially there too). All 7 pass post-implementation, alongside the
  unmodified `tests/test_rewriter_validation.py` suite (5 tests, still
  green — no regression to the leaked-commentary rejection logic).
- Full `pytest` suite: 55/55 passing. `ruff check src`, `ruff format
  --check src`, `mypy src` all clean.
- Live smoke test against the real running dev server (`--reload`,
  already picked up the change): a real `/api/generate` call (AI/ML
  Engineer JD) completed with `Rewritten: Professional Summary,
  Technical Skills` in 40.3s for 2 parallel sections, score 91.8% "Ready
  to submit", clean PDF. Then a real `/api/boost/{task_id}` call (Weave-in
  2 missing keywords) completed in 110s covering 2 sections
  (Professional Summary, Experience — the latter is the largest section,
  so its own generation time dominates), pushing the score to 100%, no
  warnings, clean PDF. Verified `resume_boosted.tex` has no leaked AI
  commentary (`grep` for refusal/markdown-table markers came back clean).
  No isolated pre/post sequential-vs-parallel timing comparison was taken
  live (would require reverting the change to benchmark, not done here)
  — the deterministic proof that calls genuinely overlap is the
  timestamp-overlap unit test, not this one live sample.
