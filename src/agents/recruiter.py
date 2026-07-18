"""Recruiter agent — extracts JD keyword requirements and compares them
against the resume, producing the keyword gap analysis the rewriter and
ATS scorer both consume.
"""

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from claude_client import ask_claude

_PROMPT = """You are a senior technical recruiter performing keyword gap analysis.

Analyze the job description and resume below.
Output ONLY a raw JSON object — no markdown fences, no explanation, just the JSON.

Required structure:
{{
  "job_title": "exact title from the JD",
  "seniority": "junior | mid | senior | lead",
  "required_keywords": ["must-have skills / tools listed in the JD"],
  "preferred_keywords": ["nice-to-have skills listed in the JD"],
  "present_in_resume": ["JD keywords that already appear in the resume"],
  "missing_from_resume": ["JD keywords NOT found in the resume"],
  "priority_adds": ["top 10 missing keywords ranked by importance — subset of missing_from_resume"],
  "key_action_verbs": ["action verbs the JD uses e.g. architect, optimize, deploy, scale"]
}}

Rules:
- present_in_resume: only skills the candidate genuinely has — do not assume
- priority_adds: max 10, ranked highest-impact first
- missing_from_resume: include both required and preferred that are absent
- key_action_verbs: these will guide how resume bullets get rewritten

JOB DESCRIPTION:
{jd}

RESUME:
{resume}
"""


def analyze(jd_text: str, resume_plain_text: str) -> dict:
    """Compare a job description against the resume and return keyword
    gap analysis (required/preferred/missing/priority keywords, action verbs)."""
    prompt = _PROMPT.format(jd=jd_text.strip(), resume=resume_plain_text.strip())
    raw = ask_claude(prompt)

    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not match:
        raise ValueError(f"Recruiter: no JSON in Claude response:\n{raw[:400]}")

    return json.loads(match.group())


if __name__ == "__main__":
    sample_jd = """
    AI/ML Engineer — Bangalore (Hybrid)

    We are building next-generation AI products and are looking for an ML Engineer
    to design, build, and deploy LLM-powered applications.

    Requirements:
    - 2+ years with Python and ML frameworks (PyTorch, TensorFlow)
    - Hands-on experience fine-tuning LLMs (LoRA, QLoRA, PEFT)
    - Building RAG pipelines using LangChain or LlamaIndex
    - Vector database experience: Pinecone, Weaviate, or Chroma
    - REST API development with FastAPI
    - Prompt engineering and evaluation techniques
    - Git and version control best practices

    Nice to have:
    - LangGraph or multi-agent framework experience
    - OpenAI / Anthropic API integration
    - AWS or Azure cloud deployment
    - Docker / containerisation experience
    - MLOps: model monitoring, CI/CD for ML pipelines
    """

    sys.path.insert(0, str(Path(__file__).parent.parent))
    from latex_parser import parse_resume

    resume_data = parse_resume()
    print("Running Recruiter Agent ...\n")
    result = analyze(sample_jd, resume_data["plain_text"])
    print(json.dumps(result, indent=2))
