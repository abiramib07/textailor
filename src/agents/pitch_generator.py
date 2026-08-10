"""Pitch Generator agent — drafts recruiter-facing self-intro material
(elevator pitch, written bio, project talking points, cover letter
template) tailored to a specific job description and resume.
"""

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from claude_client import ask_claude

_PROMPT = """You are a career coach helping a candidate prepare application \
material for one specific job. Read the job description and resume below, \
then draft four pieces of content grounded ONLY in what the resume actually \
says — never invent employers, numbers, or skills the resume doesn't have.

Output ONLY a raw JSON object — no markdown fences, no explanation, just the JSON.

Required structure:
{{
  "short_pitch": "A 30-40 second spoken elevator pitch (first person, ~80-100 \
words): name, current title/years of experience, 1-2 flagship achievements \
most relevant to this JD, core tech stack, said the way a candidate would \
say it out loud in an interview.",
  "written_bio": "A written bio for a LinkedIn About section or cold outreach \
message (150-220 words): a strong opening line, then 2-4 bullet-style \
highlights (as '- ' lines) of the achievements most relevant to this JD, \
then the tech stack, then a closing line on what the candidate cares about.",
  "project_pitches": "2-3 STAR-style talking points, one per project, chosen \
from the resume as the ones most relevant to this JD. For each: a numbered \
heading naming the project, then 3-5 sentences telling it as a story \
(what/why/how), then a likely interviewer follow-up question with a one-line \
answer. Separate each project with a blank line.",
  "cover_letter_template": "A full cover letter (250-350 words, 3-4 short \
paragraphs) using the job title and company name extracted from the JD if \
present, opening with the candidate's strongest relevant fact, one flagship \
project story tied to what this JD needs, a short paragraph mirroring 1-2 \
JD keywords against the candidate's actual stack, and a confident close. \
Sign off with the candidate's actual name, email, and phone from the \
resume's contact line. Use the literal placeholder [one specific reason \
tied to their product/mission] for the 'why this company' line since that \
requires genuine research the resume can't provide."
}}

JOB DESCRIPTION:
{jd}

RESUME:
{resume}
"""


def generate_pitches(jd_text: str, resume_plain_text: str) -> dict:
    """Draft a short pitch, written bio, project talking points, and cover
    letter template tailored to the given job description and resume."""
    prompt = _PROMPT.format(jd=jd_text.strip(), resume=resume_plain_text.strip())
    raw = ask_claude(prompt)

    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not match:
        raise ValueError(f"Pitch generator: no JSON in Claude response:\n{raw[:400]}")

    return json.loads(match.group())


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from latex_parser import parse_resume

    sample_jd = """
    AI/ML Engineer — Bangalore (Hybrid)

    We are building next-generation AI products and are looking for an ML Engineer
    to design, build, and deploy LLM-powered applications using RAG and agentic
    architectures.
    """

    resume_data = parse_resume()
    print("Running Pitch Generator Agent ...\n")
    result = generate_pitches(sample_jd, resume_data["plain_text"])
    print(json.dumps(result, indent=2))
