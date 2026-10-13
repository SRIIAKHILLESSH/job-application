"""Read the LaTeX resume and make honest, job-specific versions of it.

Tailoring only *rearranges and re-labels what is already true*:
  1. headline matches the job family (Data / DevOps / Python), all roles you have held
  2. skills inside each skills line are reordered so the job's keywords come first
  3. bullets inside each role are reordered so the most relevant ones come first
  4. skills from resume/skills_bank.yml (skills you confirmed you have but aren't on the resume) are added
     only when the job asks for them
Nothing is invented, and there is no hidden or white text. Skills the job wants that you don't have stay missing.
"""
from __future__ import annotations

import re
from pathlib import Path

import yaml

from . import skills

ROOT = Path(__file__).resolve().parent.parent
MASTER = ROOT / "resume" / "master.tex"
BANK = ROOT / "resume" / "skills_bank.yml"

HEADLINES = {
    "data": "Data Engineer | Python | DevOps | Cloud",
    "devops": "DevOps / Cloud Engineer | AWS | Terraform | CI/CD | Python",
    "python": "Python Developer | Data Engineering | AWS | DevOps",
}


def load_master() -> str:
    return MASTER.read_text(encoding="utf-8")


def load_bank() -> list[str]:
    if not BANK.exists():
        return []
    data = yaml.safe_load(BANK.read_text(encoding="utf-8")) or {}
    names = [s for s in (data.get("skills") or []) if s]
    unknown = [s for s in names if s not in skills.VOCAB]
    if unknown:
        raise ValueError(f"skills_bank.yml has names not in the vocabulary (see jobapp/skills.py): {unknown}")
    return names


def to_text(tex: str) -> str:
    """Plain text of the document body, close to what an ATS extracts from the PDF."""
    body = tex.split(r"\begin{document}", 1)[-1]
    body = re.sub(r"(?<!\\)%.*", "", body)
    body = re.sub(r"\\href\{[^}]*\}\{([^}]*)\}", r"\1", body)
    body = body.replace(r"\&", "&").replace(r"\%", "%").replace("$|$", "|").replace("--", "-")
    body = re.sub(r"\\[A-Za-z]+\*?(\[[^\]]*\])?", " ", body)
    body = re.sub(r"[{}\\]", " ", body)
    return re.sub(r"\s+", " ", body).strip()


# ---------------------------------------------------------------- tailoring
def _weight(text: str, want: dict[str, float]) -> float:
    return sum(want.get(k, 0) for k in skills.counts(text))


def _reorder_list(items: list[str], want: dict[str, float]) -> list[str]:
    return sorted(items, key=lambda s: -_weight(s, want))  # stable: ties keep the original order


def _tailor_skills(tex: str, want: dict[str, float], add: list[str]) -> str:
    def fix(m: re.Match) -> str:
        cat, items, end = m.group(1), m.group(2), m.group(3)
        parts = [p.strip() for p in re.split(r",(?![^(]*\))", items) if p.strip()]
        plain = cat.replace(r"\&", "&")
        parts += [s for s in add if skills.category(s) == plain and not any(skills.counts(p).get(s) for p in parts)]
        return rf"\textbf{{{cat}:}} " + ", ".join(_reorder_list(parts, want)) + end

    a, b = tex.split(r"\section{Technical Skills}", 1)
    sec, rest = b.split(r"\section{", 1)
    sec = re.sub(r"\\textbf\{([^}:]+):\}\s*(.+?)(\s*\\\\\s*\n|\s*\n\})", fix, sec)
    return a + r"\section{Technical Skills}" + sec + r"\section{" + rest


def _tailor_bullets(tex: str, want: dict[str, float]) -> str:
    def fix(m: re.Match) -> str:
        lines = m.group(2).strip("\n").split("\n")
        items = [ln for ln in lines if ln.strip().startswith(r"\resumeItem{")]
        if len(items) != len(lines):  # unexpected layout: leave it alone
            return m.group(0)
        return m.group(1) + "\n" + "\n".join(_reorder_list(items, want)) + "\n" + m.group(3)

    return re.sub(r"(\\resumeItemListStart)(.*?)(\\resumeItemListEnd)", fix, tex, flags=re.S)


def _tailor_summary(tex: str, want: dict[str, float]) -> str:
    def fix(m: re.Match) -> str:
        parts = [p.strip() for p in m.group(1).replace(", and ", ", ").split(",")]
        parts = _reorder_list(parts, want)
        return r"Hands-on experience with \textbf{" + ", ".join(parts[:-1]) + ", and " + parts[-1] + "}"

    return re.sub(r"Hands-on experience with \\textbf\{([^}]*)\}", fix, tex, count=1)


def tailor(tex: str, family: str, want: dict[str, float], bank: list[str]) -> tuple[str, list[str]]:
    """Return (tailored tex, bank skills that were added)."""
    have = set(skills.counts(to_text(tex)))
    add = [s for s in bank if s in want and s not in have]
    out = tex
    if family in HEADLINES:
        out = re.sub(r"(\\textbf\{)Data Engineer \| Python \| DevOps \| Cloud(\})",
                     lambda m: m.group(1) + HEADLINES[family] + m.group(2), out, count=1)
    out = _tailor_summary(out, want)
    out = _tailor_skills(out, want, add)
    out = _tailor_bullets(out, want)
    return out, add
