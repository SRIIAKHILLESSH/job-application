"""Your saved job-search links (links.yml): every job on each link is pulled out and labelled with its website.

Paste a search URL from LinkedIn, Dice, Indeed, Wellfound or Handshake. The website is detected from the URL.
- LinkedIn: public (logged-out) job list, keeping the keywords/location/filters from your URL, plus each description.
- Dice: public search pages, plus each job's page for the description.
- Indeed: blocks plain scrapers, so the search words from your URL go through JobSpy (same as the main search).
- Wellfound: public role/location pages (e.g. wellfound.com/role/r/data-engineer); the jobs are embedded in the page.
- Handshake: only shows jobs to signed-in students, so it is listed with an error instead of scraped.
"""
from __future__ import annotations

import base64
import json
import logging
import re
import time
from datetime import datetime, timezone
from urllib.parse import parse_qs, urlencode, urljoin, urlparse

import requests
import yaml

from . import store
from .sources import _job, _strip_html

log = logging.getLogger("jobapp.links")
LINKS = store.ROOT / "links.yml"
SITES = {"linkedin.": "linkedin", "dice.com": "dice", "indeed.": "indeed", "wellfound.com": "wellfound",
         "angel.co": "wellfound", "joinhandshake.": "handshake"}
SITE_NAMES = {"linkedin": "LinkedIn", "dice": "Dice", "indeed": "Indeed", "wellfound": "Wellfound",
              "handshake": "Handshake"}
BROWSER = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
                         "Chrome/130.0 Safari/537.36", "Accept-Language": "en-US,en;q=0.9"}
HEADER = ("# Your saved job-search links. Every job on each link is scanned, scored and listed on the website.\n"
          "# Edit here or in the website's \"My job links\" tab. The website is detected from the URL.\n")


class LinkError(Exception):
    """A link that can't be scraped, with a message the user can act on."""


def detect_site(url: str) -> str | None:
    host = urlparse(url.strip()).netloc.lower()
    return next((site for key, site in SITES.items() if key in host), None)


def load() -> list[dict]:
    if not LINKS.exists():
        return []
    return [x for x in yaml.safe_load(LINKS.read_text(encoding="utf-8")) or [] if x.get("url")]


def dump(links: list[dict]) -> str:
    clean = [{"name": x.get("name") or "", "url": x["url"].strip()} for x in links]
    return HEADER + (yaml.safe_dump(clean, sort_keys=False, allow_unicode=True, width=1000) if clean else "[]\n")


def save(links: list[dict]) -> str:
    text = dump(links)
    LINKS.write_text(text, encoding="utf-8")
    return text


def save_to_github(text: str, token: str, repo: str, branch: str = "main") -> None:
    """Commits links.yml to the repo so the scheduled scan sees it (the website's disk is not kept on Streamlit Cloud)."""
    api = f"https://api.github.com/repos/{repo}/contents/links.yml"
    h = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}
    r = requests.get(api, headers=h, params={"ref": branch}, timeout=20)
    sha = r.json().get("sha") if r.status_code == 200 else None
    body = {"message": "Update saved job links", "branch": branch,
            "content": base64.b64encode(text.encode()).decode()} | ({"sha": sha} if sha else {})
    r = requests.put(api, headers=h, json=body, timeout=20)
    if r.status_code not in (200, 201):
        raise LinkError(f"GitHub said {r.status_code}: {r.json().get('message', r.text[:200])}")


def _get(url: str, **kw) -> requests.Response:
    r = requests.get(url, headers=BROWSER, timeout=30, **kw)
    if r.status_code in (401, 403, 429, 999):
        raise LinkError(f"the site blocked the request (HTTP {r.status_code}); try again later")
    r.raise_for_status()
    return r


def _soup(text: str):
    from bs4 import BeautifulSoup  # only needed for link scraping
    return BeautifulSoup(text, "html.parser")


def _txt(el) -> str:
    return el.get_text(" ", strip=True) if el else ""


# ---------------------------------------------------------------- LinkedIn
def linkedin(url: str, limit: int, details: bool = True) -> list[dict]:
    q = parse_qs(urlparse(url).query)
    params = {k: v[0] for k, v in q.items() if k in ("keywords", "location", "geoId", "distance") or k.startswith("f_")}
    out, seen = [], set()
    for start in range(0, limit, 10):
        api = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search?" + urlencode(params | {"start": start})
        cards = _soup(_get(api).text).select("div.base-card")
        if not cards:
            break
        for c in cards:
            jid = (c.get("data-entity-urn") or "").rsplit(":", 1)[-1]
            if not jid or jid in seen:
                continue
            seen.add(jid)
            t = c.select_one("time")
            out.append(_job("linkedin", _txt(c.select_one(".base-search-card__subtitle")),
                            _txt(c.select_one(".base-search-card__title")),
                            _txt(c.select_one(".job-search-card__location")),
                            f"https://www.linkedin.com/jobs/view/{jid}/", t.get("datetime", "") if t else "", ""))
        time.sleep(1)
    out = out[:limit]
    if details:
        for j in out:
            jid = j["url"].rstrip("/").rsplit("/", 1)[-1]
            try:
                d = _soup(_get(f"https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{jid}").text)
                j["description"] = _strip_html(str(d.select_one(".show-more-less-html__markup") or ""))
            except Exception as e:  # rate-limited: keep the job, it shows as "No description"
                log.info("linkedin description %s: %s", jid, e)
            time.sleep(1)
    return out


# ---------------------------------------------------------------- Dice
def dice(url: str, limit: int, details: bool = True) -> list[dict]:
    parts = urlparse(url)
    q = parse_qs(parts.query)
    out, seen = [], set()
    for page in range(1, 20):
        if len(out) >= limit:
            break
        q["page"] = [str(page)]
        cards = _soup(_get(parts._replace(query=urlencode(q, doseq=True)).geturl()).text).select('[data-testid="job-card"]')
        new = 0
        for c in cards:
            a = c.select_one('[data-testid="job-search-job-detail-link"]')
            if not a or not a.get("href"):
                continue
            href = urljoin("https://www.dice.com", a["href"])
            if href in seen:
                continue
            seen.add(href)
            new += 1
            line = next((_txt(p) for p in c.select("p") if "•" in p.get_text()), "")  # "Charlotte, NC • Today"
            out.append(_job("dice", _txt(c.select_one('[data-testid="job-card-company-name"]')), _txt(a),
                            line.split("•")[0].strip(), href, "", ""))
        if not new:
            break
    out = out[:limit]
    if details:
        for j in out:
            try:
                posting = _jsonld(_get(j["url"]).text)
            except Exception as e:
                log.info("dice description %s: %s", j["url"], e)
                continue
            if posting:
                j["description"] = _strip_html(posting.get("description"))
                j["posted"] = (posting.get("datePosted") or "")[:10]
                j["company"] = j["company"] or (posting.get("hiringOrganization") or {}).get("name", "")
            time.sleep(0.5)
    return out


def _jsonld(page: str) -> dict | None:
    for m in re.finditer(r'<script type="application/ld\+json"[^>]*>(.*?)</script>', page, re.S):
        try:
            data = json.loads(m.group(1))
        except ValueError:
            continue
        for item in data if isinstance(data, list) else data.get("@graph", [data]):
            if isinstance(item, dict) and item.get("@type") == "JobPosting":
                return item
    return None


# ---------------------------------------------------------------- Wellfound
def wellfound(url: str, limit: int, details: bool = True) -> list[dict]:
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', _get(url).text, re.S)
    if not m:
        raise LinkError("Wellfound showed a captcha or a sign-in page; use a public page like wellfound.com/role/r/data-engineer")
    data = json.loads(m.group(1))["props"]["pageProps"].get("apolloState", {}).get("data", {})
    company = {ref.get("__ref"): v.get("name", "") for v in data.values() if v.get("__typename") == "StartupResult"
               for ref in v.get("highlightedJobListings") or []}
    out = []
    for key, j in data.items():
        if j.get("__typename") != "JobListingSearchResult":
            continue
        locs = (j.get("locationNames") or []) + (["Remote"] if j.get("remote") else [])
        posted = datetime.fromtimestamp(j["liveStartAt"], timezone.utc).date().isoformat() if j.get("liveStartAt") else ""
        out.append(_job("wellfound", company.get(key, ""), j.get("title"), ", ".join(locs),
                        f"https://wellfound.com/jobs/{j.get('id')}-{j.get('slug', '')}", posted,
                        j.get("description") or "", remote=bool(j.get("remote")) or None))
    if not out:
        raise LinkError("no jobs on this page (Wellfound search pages need sign-in; use a /role/ page)")
    return out[:limit]


# ---------------------------------------------------------------- Indeed (via JobSpy) and Handshake
def indeed(url: str, limit: int, details: bool = True) -> list[dict]:
    q = {k: v[0] for k, v in parse_qs(urlparse(url).query).items()}
    if not q.get("q"):
        raise LinkError("use an Indeed search URL with search words, e.g. indeed.com/jobs?q=data+engineer&l=Remote")
    from jobspy import scrape_jobs

    days = int(q["fromage"]) if q.get("fromage", "").isdigit() else None
    df = scrape_jobs(site_name=["indeed"], search_term=q["q"], location=q.get("l") or "United States",
                     results_wanted=limit, hours_old=days * 24 if days else None, country_indeed="USA",
                     description_format="markdown", verbose=0)
    out = []
    for r in df.fillna("").to_dict("records"):
        if r.get("job_url"):
            out.append(_job("indeed", r.get("company"), r.get("title"), r.get("location"), r["job_url"],
                            str(r.get("date_posted") or "")[:10], r.get("description") if details else "",
                            remote=bool(r.get("is_remote")) if r.get("is_remote") != "" else None))
    return out


def handshake(url: str, limit: int, details: bool = True) -> list[dict]:
    raise LinkError("Handshake only shows jobs after you sign in with your school account, so it can't be scanned. "
                    "Turn on Handshake's job-alert emails instead.")


SCRAPERS = {"linkedin": linkedin, "dice": dice, "indeed": indeed, "wellfound": wellfound, "handshake": handshake}


def scrape(link: dict, limit: int = 50, details: bool = True) -> list[dict]:
    """All jobs on one saved link. Raises LinkError with a readable reason when the link can't be scanned."""
    site = detect_site(link["url"])
    if not site:
        raise LinkError("unknown website; use a LinkedIn, Dice, Indeed, Wellfound or Handshake link")
    try:
        jobs = SCRAPERS[site](link["url"], limit, details)
    except LinkError:
        raise
    except requests.RequestException as e:
        raise LinkError(f"network error: {e.__class__.__name__}") from e
    except Exception as e:  # the site changed its page layout
        raise LinkError(f"couldn't read the page ({e.__class__.__name__}: {e})") from e
    for j in jobs:
        j["link_name"] = link.get("name") or ""
    return jobs


def collect(cfg: dict) -> tuple[list[dict], dict]:
    limit = (cfg.get("links") or {}).get("max_jobs_per_link", 50)
    jobs, report = [], {}
    for link in load():
        site = detect_site(link["url"]) or "unknown"
        key = f"link:{site}:{link.get('name') or link['url'][:60]}"
        try:
            got = scrape(link, limit)
            jobs += got
            report[key] = len(got)
        except LinkError as e:
            report[key] = f"error: {e}"
            log.warning("%s failed: %s", key, e)
    return jobs, report
