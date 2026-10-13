# AI Job Application

Finds Data / DevOps / Python jobs every day, checks them against your resume, makes a tailored resume when the
match is below 90%, and keeps every relevant job link in a database you browse on a website. It follows the
architecture diagram in this repo (`WhatsApp Image 2026-10-13 at 15.20.38.jpeg`). **It never applies for you.**

```
LinkedIn, Indeed            ┐
Greenhouse / Lever / Ashby  ┘─► scrape jobs ─► filter (title, US/remote, age, seniority) ─► ATS check vs resume/master.tex
        ATS ≥ 90  ─────────────────────────────► job links database (master resume)
        50 ≤ ATS < 90 ─► tailored resume (.tex + PDF) ─► job links database
        ATS < 50  ─► skipped (not relevant)
```

## Where things are
| Path | What |
|---|---|
| `config.yml` | job titles, exclusions, search terms, company boards, thresholds (90 / 50) |
| `resume/master.tex` | your resume (the Overleaf source). Edit it here or paste back from Overleaf. |
| `resume/skills_bank.yml` | skills you really have that aren't on the resume; added only when a job asks for them |
| `jobapp/sources.py` | scrapers: Greenhouse, Lever, Ashby (official public APIs), LinkedIn + Indeed (public guest search via JobSpy) |
| `jobapp/filters.py` | title family, US/remote, posting age |
| `jobapp/skills.py`, `jobapp/ats.py` | skill vocabulary and the ATS keyword score |
| `jobapp/resume.py` | LaTeX → text, and the honest tailoring |
| `jobapp/run.py` | the pipeline (`python -m jobapp.run`) |
| `data/jobs/YYYY-MM.jsonl` | **the job links database** (append-only) |
| `resumes/<job id>.tex` | tailored resumes; PDFs are attached to each scan's GitHub Release |
| `app.py` | the website (Streamlit) |
| `.github/workflows/scan.yml` | runs the pipeline at 8 AM and 6 PM Eastern, builds PDFs, commits the database |

## The ATS score
Share of the job's skill keywords (weighted by how often they're mentioned, double if in the title) that appear on
the resume. Jobs naming fewer than 6 skills are scaled down. Real ATS systems differ by vendor and aren't public;
this is a transparent, repeatable stand-in.

## Tailoring rules (what "change the resume" means)
1. Headline matches the job family (Data / DevOps / Python), all roles you've held.
2. Skills inside each skills line and bullets inside each job are reordered so the job's keywords come first.
3. Skills from `resume/skills_bank.yml` are added only when the job asks for them.

Nothing is invented and there is no hidden text. A skill the job wants that you don't have stays in **Missing**.
That's why many jobs stay below 90 after tailoring. To raise them honestly, add real skills to the skills bank.

## Sources not covered
Handshake, Wellfound and Dice only show jobs to signed-in users, so they aren't scraped. Most startups on Wellfound
also post on Greenhouse/Lever/Ashby; add their board names to `config.yml`. LinkedIn sometimes withholds full
descriptions (rate limit); those jobs are listed as "No description" and not scored.

## Run locally
```
python -m venv .venv && .venv/Scripts/python -m pip install -r requirements.txt
.venv/Scripts/python -m pytest -q
.venv/Scripts/python -m jobapp.run --dry-run        # counts only
.venv/Scripts/python -m jobapp.run                  # writes data/ and resumes/
.venv/Scripts/streamlit run app.py
```
