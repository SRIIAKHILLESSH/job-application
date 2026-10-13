"""One pass of the pipeline in the architecture diagram:

  sources -> scrape jobs -> load resume -> relevance + ATS check
      ATS >= ats_ready         -> job link to the database (master resume)
      min_relevance <= ATS < ats_ready -> tailor the resume, re-score, job link + tailored resume to the database
      ATS < min_relevance      -> not relevant, skipped

Run: python -m jobapp.run            (add --no-search to skip LinkedIn/Indeed, --dry-run to write nothing)
"""
from __future__ import annotations

import argparse
import json
import logging
import os
from datetime import datetime, timezone

import yaml

from . import ats, filters, resume, sources, store

CONFIG = store.ROOT / "config.yml"
BUILD = store.ROOT / "build"


def load_config() -> dict:
    return yaml.safe_load(CONFIG.read_text(encoding="utf-8"))


def pdf_url(name: str) -> str:
    repo, tag = os.environ.get("GITHUB_REPOSITORY"), os.environ.get("RELEASE_TAG")
    return f"https://github.com/{repo}/releases/download/{tag}/{name}.pdf" if repo and tag else ""


def collect(cfg: dict, use_search: bool) -> tuple[list[dict], dict]:
    jobs, report = sources.boards(cfg)
    if use_search:
        more, rep2 = sources.search(cfg)
        jobs += more
        report.update(rep2)
    return jobs, report


def process(jobs: list[dict], cfg: dict, seen: set[str], master_tex: str, bank: list[str], now: str) -> dict:
    th = cfg["thresholds"]
    master_text = resume.to_text(master_tex)
    counts = {"fetched": len(jobs), "title_match": 0, "us_or_remote": 0, "fresh": 0, "new": 0,
              "no_description": 0, "too_senior": 0, "not_relevant": 0, "ready": 0, "tailored": 0, "not_tailored": 0}

    # 1. cheap filters + de-duplication (same company + title from several sources -> keep the one with a description)
    best: dict[str, dict] = {}
    for j in jobs:
        fam = filters.family(j["title"], cfg)
        if not fam:
            continue
        counts["title_match"] += 1
        if not filters.us_or_remote(j["location"], j.get("remote")):
            continue
        counts["us_or_remote"] += 1
        if not filters.fresh(j["posted"], th["max_age_days"]):
            continue
        counts["fresh"] += 1
        key = store.norm_key(j["company"], j["title"])
        if j["id"] in seen or key in seen:
            continue
        j["family"] = fam
        if key not in best or len(j["description"]) > len(best[key]["description"]):
            best[key] = j
    new = list(best.values())
    counts["new"] = len(new)

    # 2. relevance + ATS check
    keep, seen_now = [], set()
    for j in new:
        seen_now |= {j["id"], store.norm_key(j["company"], j["title"])}
        rec = {k: j[k] for k in ("id", "source", "company", "title", "location", "url", "posted", "family")}
        rec |= {"found_utc": now, "flags": ats.flags(j["description"]), "years_required": ats.years_required(j["description"])}
        if len(j["description"]) < 200:
            counts["no_description"] += 1
            keep.append(rec | {"decision": "no_description", "ats_before": None, "ats_after": None, "matched": [],
                               "missing": [], "added_skills": [], "resume": "", "pdf": "", "description": ""})
            continue
        if rec["years_required"] and rec["years_required"] > th["max_years_required"]:
            counts["too_senior"] += 1
            continue
        s = ats.score(j["title"], j["description"], master_text)
        if s["ats"] is None or s["ats"] < th["min_relevance"]:
            counts["not_relevant"] += 1
            continue
        keep.append(rec | {"ats_before": s["ats"], "ats_after": s["ats"], "matched": s["matched"], "missing": s["missing"],
                           "n_keywords": s["n_keywords"], "added_skills": [], "resume": "resume/master.tex",
                           "pdf": pdf_url("master"), "description": j["description"][:8000], "_desc": j["description"],
                           "decision": "ready" if s["ats"] >= th["ats_ready"] else "to_tailor"})

    # 3. tailor the ones below the bar (highest scores first, capped per run)
    to_tailor = sorted((r for r in keep if r["decision"] == "to_tailor"), key=lambda r: -r["ats_before"])
    for i, r in enumerate(to_tailor):
        if i >= th["max_tailor_per_run"]:
            r["decision"] = "not_tailored"
            continue
        want = ats.job_keywords(r["title"], r["_desc"])
        tex, added = resume.tailor(master_tex, r["family"], want, bank)
        r["ats_after"] = ats.score(r["title"], r["_desc"], resume.to_text(tex))["ats"]
        r["added_skills"] = added
        r["missing"] = [m for m in r["missing"] if m not in added]
        r["matched"] = r["matched"] + added
        r["resume"] = f"resumes/{r['id']}.tex"
        r["pdf"] = pdf_url(r["id"])
        r["decision"] = "tailored"
        r["_tex"] = tex
    for r in keep:
        r.pop("_desc", None)
        if r["decision"] in counts:
            counts[r["decision"]] += 1
    return {"records": keep, "seen": seen_now, "counts": counts}


def main(argv=None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-search", action="store_true", help="skip LinkedIn/Indeed")
    ap.add_argument("--dry-run", action="store_true", help="print counts, write nothing")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    cfg = load_config()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    jobs, report = collect(cfg, use_search=not a.no_search)
    out = process(jobs, cfg, store.load_seen(), resume.load_master(), resume.load_bank(), now)
    print(json.dumps(out["counts"], indent=2))
    if a.dry_run:
        return

    BUILD.mkdir(exist_ok=True)
    store.RESUMES.mkdir(exist_ok=True)
    compile_list = ["resume/master.tex"]
    for r in out["records"]:
        tex = r.pop("_tex", None)
        if tex:
            (store.ROOT / r["resume"]).write_text(tex, encoding="utf-8")
            compile_list.append(r["resume"])
    store.append(out["records"], now[:7])
    store.add_seen(out["seen"])
    if out["records"]:
        (BUILD / "to_compile.txt").write_text("\n".join(compile_list) + "\n", encoding="utf-8")
    (store.DATA / "last_run.json").write_text(json.dumps({"run_utc": now, "counts": out["counts"], "sources": report},
                                                         indent=2, sort_keys=True), encoding="utf-8")


if __name__ == "__main__":
    main()
