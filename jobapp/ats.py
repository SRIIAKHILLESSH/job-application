"""ATS-style keyword score: how much of what the job asks for is visible on the resume.

Score = weighted share of the job's skill keywords that also appear on the resume (0-100).
A keyword's weight grows with how often the job mentions it (capped) and doubles if it is in the job title.
Jobs that name fewer than MIN_KEYWORDS skills are scaled down (3 of 3 matched is weak evidence, not a 100% fit).
This is a transparent stand-in for real ATS filters, which differ by vendor and are not public.
"""
from __future__ import annotations

import re

from . import skills

MIN_KEYWORDS = 6

_YEARS = re.compile(r"(\d{1,2})\s*\+?\s*(?:-\s*\d{1,2}\s*)?(?:years?|yrs?)\b(?:\s+of)?(?:\s+\w+){0,4}?\s+(?:experience|exp)", re.I)
_CLEARANCE = re.compile(r"security clearance|\bts/sci\b|top secret|secret clearance|must be a u\.?s\.? citizen|"
                        r"u\.?s\.? citizenship (is )?required|active clearance", re.I)
_NO_SPONSOR = re.compile(r"(not|unable to|cannot|can't|won't|will not) (provide |offer )?(visa )?sponsor|"
                         r"without (the need for )?(current or future )?(visa )?sponsorship|no (visa )?sponsorship", re.I)


def job_keywords(title: str, description: str) -> dict[str, float]:
    body = skills.counts(description)
    head = skills.counts(title)
    return {k: (1 + 0.5 * min(n - 1, 2)) * (2 if k in head else 1) for k, n in (body + head).items()}


def score(title: str, description: str, resume_text: str) -> dict:
    want = job_keywords(title, description)
    have = set(skills.counts(resume_text))
    total = sum(want.values())
    matched = sorted((k for k in want if k in have), key=lambda k: -want[k])
    missing = sorted((k for k in want if k not in have), key=lambda k: -want[k])
    return {
        "ats": round(100 * sum(want[k] for k in matched) / total * min(1, len(want) / MIN_KEYWORDS), 1) if total else None,
        "matched": matched,
        "missing": missing,
        "n_keywords": len(want),
    }


def years_required(description: str) -> int | None:
    ys = [int(m.group(1)) for m in _YEARS.finditer(description or "") if int(m.group(1)) <= 20]
    return min(ys) if ys else None


def flags(description: str) -> list[str]:
    out = []
    if _CLEARANCE.search(description or ""):
        out.append("clearance/citizenship")
    if _NO_SPONSOR.search(description or ""):
        out.append("no sponsorship")
    return out
