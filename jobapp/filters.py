"""Cheap filters applied before any scoring: title family, seniority, US/remote location, posting age."""
from __future__ import annotations

import re
from datetime import date, timedelta

STATES = ("Alabama Alaska Arizona Arkansas California Colorado Connecticut Delaware Florida Georgia Hawaii Idaho "
          "Illinois Indiana Iowa Kansas Kentucky Louisiana Maine Maryland Massachusetts Michigan Minnesota "
          "Mississippi Missouri Montana Nebraska Nevada New_Hampshire New_Jersey New_Mexico New_York North_Carolina "
          "North_Dakota Ohio Oklahoma Oregon Pennsylvania Rhode_Island South_Carolina South_Dakota Tennessee Texas "
          "Utah Vermont Virginia Washington West_Virginia Wisconsin Wyoming District_of_Columbia").split()
STATES = [s.replace("_", " ") for s in STATES]
ABBR = ("AL AK AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC ND OH OK "
        "OR PA RI SC SD TN TX UT VT VA WA WV WI WY DC").split()
CITIES = ("san francisco|new york|nyc|seattle|austin|boston|chicago|los angeles|denver|atlanta|detroit|dallas|"
          "houston|miami|portland|phoenix|san diego|san jose|palo alto|mountain view|menlo park|sunnyvale|"
          "redwood city|south san francisco|bay area|washington dc|arlington|pittsburgh|philadelphia|"
          "salt lake city|raleigh|minneapolis|nashville|columbus|ann arbor|southfield|troy|plano|irvine")
US = re.compile(r"united states|\bU\.?S\.?A?\b|\bAmerica\b|" + "|".join(rf"\b{s}\b" for s in STATES)
                + rf"|\b({CITIES})\b", re.I)
US_ABBR = re.compile("|".join(rf",\s*{a}\b" for a in ABBR))  # "Austin, TX" (case-sensitive)
FOREIGN = re.compile(r"canada|toronto|vancouver|montreal|united kingdom|\buk\b|london|ireland|dublin|germany|berlin|"
                     r"munich|france|paris|spain|madrid|barcelona|netherlands|amsterdam|poland|warsaw|india|bangalore|"
                     r"bengaluru|hyderabad|pune|mumbai|delhi|singapore|japan|tokyo|australia|sydney|melbourne|"
                     r"brazil|s[aã]o paulo|mexico|argentina|colombia|israel|tel aviv|emea|apac|latam|europe|korea|"
                     r"seoul|china|taiwan|hong kong|philippines|switzerland|zurich|sweden|stockholm|denmark|"
                     r"copenhagen|portugal|lisbon|romania|serbia|costa rica|chile|new zealand|uae|dubai", re.I)
REMOTE = re.compile(r"\bremote\b|anywhere|distributed", re.I)


def family(title: str, cfg: dict) -> str | None:
    t = title or ""
    if any(re.search(p, t, re.I) for p in cfg.get("exclude_titles", [])):
        return None
    for fam, pats in (cfg.get("titles") or {}).items():
        if any(re.search(p, t, re.I) for p in pats):
            return fam
    return None


def us_or_remote(location: str, remote) -> bool:
    loc = location or ""
    if US.search(loc):
        return True
    if FOREIGN.search(loc):
        return False
    if US_ABBR.search(loc):
        return True
    return bool(remote) or bool(REMOTE.search(loc)) or not loc.strip()


def fresh(posted: str, max_age_days: int, today: date | None = None) -> bool:
    if not posted:
        return True
    try:
        d = date.fromisoformat(posted[:10])
    except ValueError:
        return True
    return d >= (today or date.today()) - timedelta(days=max_age_days)
