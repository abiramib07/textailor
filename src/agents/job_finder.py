"""Job finder agent — searches the web for real, currently open job
postings matching the candidate's criteria, for the Application Tracker's
"Find Jobs" action. Streams a live trace of each search/fetch it runs
(so a caller can show progress instead of a silent multi-minute wait),
grounded in real WebSearch/WebFetch results; never fabricates a company,
role, link, or salary figure.
"""

import json
import re
import sys
from collections.abc import Iterator
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from claude_client import stream_claude

_TIMEOUT_SECONDS = 480  # web search takes several rounds — longer than a plain text call
_ALLOWED_TOOLS = "WebSearch,WebFetch"

_PROMPT = """You are a job-search research assistant. Use WebSearch (and WebFetch if you \
need to read a specific page) to find real, currently open job postings — never invent a \
company, role, URL, or salary figure.

Search criteria:
- Role / skills: {query}
- Years of experience: {years_experience}
- Location: {location}
- Number of postings requested: {count}
{salary_clause}

Search job boards and company career pages (LinkedIn, Naukri, Wellfound, Indeed, \
Glassdoor, individual company sites) for real, individually-linked postings matching \
the criteria above. For each one you find:
- Classify "tier" as one of: Product, GCC, Services, Startup, or Unclear (use Unclear \
  when the posting is from a staffing agency or individual recruiter rather than the \
  hiring company itself).
- In "notes", flag anything worth knowing: recruiter-posted, salary not disclosed in \
  the posting, how many years the posting actually asks for if different from the \
  request, posting date if visible, or similar.

If you find fewer than {count} genuine postings, return however many you actually \
found — do not pad the list with fabricated, duplicated, or unrelated entries.

Output ONLY a raw JSON object (no markdown fences, no explanation outside JSON):
{{
  "postings": [
    {{
      "company": "exact company or agency name from the posting",
      "tier": "Product | GCC | Services | Startup | Unclear",
      "role_title": "exact role title from the posting",
      "job_link": "the real URL of this specific posting",
      "salary_evidence": "what you found about likely compensation and its source (e.g. 'AmbitionBox: avg 28L for this role/company'), or empty string if you found nothing",
      "notes": "one short sentence flagging anything worth knowing, or empty string"
    }}
  ],
  "search_note": "one sentence: how many postings found vs requested, plus any caveat about staleness, agencies, salary-evidence coverage, or search coverage"
}}
"""

_SALARY_CLAUSE = """- Minimum target compensation: {min_salary_lpa} LPA (lakhs per annum, India)

Indian job postings almost never state salary directly, so for each candidate posting \
also search salary-aggregator sources (AmbitionBox, Glassdoor, Levels.fyi, Naukri salary \
insights, Payscale) for that company and role/seniority level. Only include a posting if \
you find real evidence (a source you can name) suggesting typical compensation at or \
above {min_salary_lpa} LPA for that role at that company — exclude it if you find no \
supporting evidence, rather than assuming a company pays well. Put the evidence and its \
source in "salary_evidence" for every included posting."""


def stream_find_jobs(
    query: str,
    years_experience: int,
    location: str,
    count: int = 15,
    min_salary_lpa: int | None = None,
) -> Iterator[dict]:
    """Search the web for real, currently open job postings matching the
    given criteria, yielding progress as it goes.

    Yields dicts of one of two shapes:
    - `{"type": "trace", "text": "..."}` — a human-readable line for each
      search/fetch the agent performs, in real time.
    - `{"type": "done", "data": {...}}` or `{"type": "error", "text": "..."}`
      — exactly one of these is yielded last. `data` has keys `postings`
      (company/tier/role_title/job_link/salary_evidence/notes) and
      `search_note` (a caveat sentence, e.g. how many were actually found).
    """
    salary_clause = _SALARY_CLAUSE.format(min_salary_lpa=min_salary_lpa) if min_salary_lpa else ""
    prompt = _PROMPT.format(
        query=query.strip(),
        years_experience=years_experience,
        location=location.strip(),
        count=count,
        salary_clause=salary_clause,
    )

    final_text: str | None = None
    for event in stream_claude(prompt, allowed_tools=_ALLOWED_TOOLS, timeout=_TIMEOUT_SECONDS):
        etype = event.get("type")
        if etype == "assistant":
            for block in event.get("message", {}).get("content", []):
                if block.get("type") != "tool_use":
                    continue
                name = block.get("name")
                tool_input = block.get("input", {})
                if name == "WebSearch":
                    yield {"type": "trace", "text": f"Searching: {tool_input.get('query', '')}"}
                elif name == "WebFetch":
                    yield {"type": "trace", "text": f"Reading: {tool_input.get('url', '')}"}
        elif etype == "result":
            final_text = event.get("result", "")

    if final_text is None:
        yield {"type": "error", "text": "Claude CLI ended without a final result."}
        return

    match = re.search(r"\{.*\}", final_text, re.DOTALL)
    if not match:
        yield {"type": "error", "text": f"No JSON in Claude response:\n{final_text[:400]}"}
        return

    data: dict = json.loads(match.group())
    data.setdefault("postings", [])
    data.setdefault("search_note", "")
    yield {"type": "done", "data": data}


if __name__ == "__main__":
    print("Running Job Finder Agent ...\n")
    for evt in stream_find_jobs(
        "GenAI RAG LangGraph AI/ML engineer", 3, "India", count=5, min_salary_lpa=25
    ):
        if evt["type"] == "trace":
            print("...", evt["text"])
        elif evt["type"] == "done":
            print(json.dumps(evt["data"], indent=2))
        else:
            print("ERROR:", evt["text"])
