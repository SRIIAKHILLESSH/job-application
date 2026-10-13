"""The job links database: append-only JSON Lines, one file per month, plus a list of job ids already seen.

Text files instead of a binary database so every cloud run commits a small, readable diff.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
JOBS = DATA / "jobs"
SEEN = DATA / "seen.txt"
RESUMES = ROOT / "resumes"


def norm_key(company: str, title: str) -> str:
    return f"{(company or '').lower().strip()}|{(title or '').lower().strip()}"


def load_seen() -> set[str]:
    return set(SEEN.read_text(encoding="utf-8").split("\n")) - {""} if SEEN.exists() else set()


def add_seen(keys) -> None:
    keys = sorted(set(keys) - load_seen())
    if keys:
        DATA.mkdir(parents=True, exist_ok=True)
        with SEEN.open("a", encoding="utf-8") as f:
            f.write("\n".join(keys) + "\n")


def append(records: list[dict], month: str) -> None:
    if not records:
        return
    JOBS.mkdir(parents=True, exist_ok=True)
    with (JOBS / f"{month}.jsonl").open("a", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def load_all() -> list[dict]:
    out = []
    for p in sorted(JOBS.glob("*.jsonl")) if JOBS.exists() else []:
        out += [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]
    return out
