"""Job sources. Every source returns a list of dicts with the same keys (see `_job`).

- Greenhouse / Lever / Ashby: official public job-board APIs (no login).
- LinkedIn / Indeed: public guest search through JobSpy (no login). LinkedIn often rate-limits full descriptions;
  those jobs are kept with an empty description and are not scored.
Handshake, Wellfound and Dice need a signed-in account, so they are not scraped.
"""
from __future__ import annotations

import concurrent.futures as cf
import hashlib
import html
import logging
import re
from datetime import datetime, timezone

import requests

log = logging.getLogger("jobapp.sources")
UA = {"User-Agent": "job-application-scanner (personal job search)"}


def job_id(source: str, url: str) -> str:
    return hashlib.sha1(f"{source}|{url}".encode()).hexdigest()[:12]


def _job(source, company, title, location, url, posted, description, remote=None) -> dict:
    return {"id": job_id(source, url), "source": source, "company": (company or "").strip(),
            "title": (title or "").strip(), "location": (location or "").strip(), "url": url,
            "posted": posted or "", "description": description or "", "remote": remote}


def _strip_html(s: str) -> str:
    s = html.unescape(s or "")
    s = re.sub(r"<(br|/p|/li|/h\d|/div)[^>]*>", "\n", s, flags=re.I)
    s = re.sub(r"<li[^>]*>", "\n- ", s, flags=re.I)
    s = re.sub(r"<[^>]+>", " ", s)
    s = html.unescape(s)
    return re.sub(r"[ \t]+", " ", re.sub(r"\n\s*\n+", "\n\n", s)).strip()


def _iso_ms(ms) -> str:
    return datetime.fromtimestamp(ms / 1000, timezone.utc).date().isoformat() if ms else ""


def greenhouse(token: str) -> list[dict]:
    r = requests.get(f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true", headers=UA, timeout=40)
    r.raise_for_status()
    out = []
    for j in r.json().get("jobs", []):
        company = j.get("company_name") or token
        out.append(_job("greenhouse", company, j.get("title"), (j.get("location") or {}).get("name"),
                        j.get("absolute_url"), (j.get("first_published") or j.get("updated_at") or "")[:10], _strip_html(j.get("content"))))
    return out


def lever(token: str) -> list[dict]:
    r = requests.get(f"https://api.lever.co/v0/postings/{token}?mode=json", headers=UA, timeout=40)
    r.raise_for_status()
    out = []
    for j in r.json():
        cat = j.get("categories") or {}
        lists = "\n".join(f"{x.get('text', '')}\n{_strip_html(x.get('content'))}" for x in j.get("lists") or [])
        desc = "\n\n".join(filter(None, [j.get("descriptionPlain"), lists, j.get("additionalPlain")]))
        loc = cat.get("location") or ", ".join(cat.get("allLocations") or [])
        out.append(_job("lever", token, j.get("text"), loc, j.get("hostedUrl"), _iso_ms(j.get("createdAt")), desc,
                        remote=(j.get("workplaceType") == "remote") or None))
    return out


def ashby(token: str) -> list[dict]:
    r = requests.get(f"https://api.ashbyhq.com/posting-api/job-board/{token}", headers=UA, timeout=40)
    r.raise_for_status()
    out = []
    for j in r.json().get("jobs", []):
        if j.get("isListed") is False:
            continue
        locs = [j.get("location") or ""] + [x.get("location", "") for x in j.get("secondaryLocations") or []]
        out.append(_job("ashby", token, j.get("title"), " / ".join(filter(None, locs)), j.get("jobUrl"),
                        (j.get("publishedAt") or "")[:10], j.get("descriptionPlain") or _strip_html(j.get("descriptionHtml")),
                        remote=j.get("isRemote")))
    return out


BOARD_FETCHERS = {"greenhouse": greenhouse, "lever": lever, "ashby": ashby}


def boards(cfg: dict) -> tuple[list[dict], dict]:
    jobs, report = [], {}
    tasks = [(kind, t) for kind, toks in (cfg.get("boards") or {}).items() for t in toks or []]
    with cf.ThreadPoolExecutor(12) as ex:
        futs = {ex.submit(BOARD_FETCHERS[k], t): (k, t) for k, t in tasks}
        for f in cf.as_completed(futs):
            k, t = futs[f]
            try:
                got = f.result()
                jobs += got
                report[f"{k}:{t}"] = len(got)
            except Exception as e:  # one dead board must not stop the run
                report[f"{k}:{t}"] = f"error: {e.__class__.__name__}"
                log.warning("board %s:%s failed: %s", k, t, e)
    return jobs, report


def search(cfg: dict) -> tuple[list[dict], dict]:
    """LinkedIn / Indeed guest search through JobSpy."""
    s = cfg.get("search") or {}
    if not s.get("sites"):
        return [], {}
    from jobspy import scrape_jobs  # heavy import, only when used

    jobs, report = [], {}
    for site in s["sites"]:
        for term in s.get("terms", []):
            key = f"{site}:{term}"
            try:
                df = scrape_jobs(site_name=[site], search_term=term, location=s.get("location", "United States"),
                                 results_wanted=s.get("results_per_term", 40), hours_old=s.get("hours_old", 30),
                                 country_indeed="USA", fetch_description=True, description_format="markdown",
                                 verbose=0)
            except Exception as e:
                report[key] = f"error: {e.__class__.__name__}"
                log.warning("search %s failed: %s", key, e)
                continue
            report[key] = len(df)
            for r in df.fillna("").to_dict("records"):
                url = r.get("job_url") or r.get("job_url_direct")
                if not url:
                    continue
                posted = r.get("date_posted")
                jobs.append(_job(site, r.get("company"), r.get("title"), r.get("location"), url,
                                 str(posted)[:10] if posted else "", r.get("description"),
                                 remote=bool(r.get("is_remote")) if r.get("is_remote") != "" else None))
    return jobs, report
