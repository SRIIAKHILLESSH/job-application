# AI Job Application

Finds Data / DevOps / Python jobs every day, checks them against your resume, makes a tailored resume when the
match is below 90%, and keeps every relevant job link in a database you browse on a website. It follows the
architecture diagram in this repo (`WhatsApp Image 2026-10-13 at 15.20.38.jpeg`). **It never applies for you.**

```
Your saved links           ┐
LinkedIn, Indeed            │
Greenhouse / Lever / Ashby  ┘─► scrape jobs ─► filter (title, US/remote, age, seniority) ─► ATS check vs resume/master.tex
        ATS ≥ 90  ─────────────────────────────► job links database (master resume)
        50 ≤ ATS < 90 ─► tailored resume (.tex + PDF) ─► job links database
        ATS < 50  ─► skipped (not relevant)
```

## Where things are
| Path | What |
|---|---|
| `links.yml` | **your saved search links** (LinkedIn, Dice, Indeed, Wellfound, Handshake). Add them on the website. |
| `config.yml` | job titles, exclusions, search terms, company boards, thresholds (90 / 50) |
| `resume/master.tex` | your resume (the Overleaf source). Edit it here or paste back from Overleaf. |
| `resume/skills_bank.yml` | skills you really have that aren't on the resume; added only when a job asks for them |
| `jobapp/links.py` | pulls every job off each saved link and labels it with its website |
| `jobapp/sources.py` | scrapers: Greenhouse, Lever, Ashby (official public APIs), LinkedIn + Indeed (public guest search via JobSpy) |
| `jobapp/filters.py` | title family, US/remote, posting age |
| `jobapp/skills.py`, `jobapp/ats.py` | skill vocabulary and the ATS keyword score |
| `jobapp/resume.py` | LaTeX → text, and the honest tailoring |
| `jobapp/run.py` | the pipeline (`python -m jobapp.run`) |
| `data/jobs/YYYY-MM.jsonl` | **the job links database** (append-only) |
| `resumes/<job id>.tex` | tailored resumes; PDFs are attached to each scan's GitHub Release |
| `app.py` | the website (Streamlit) |
| `.github/workflows/scan.yml` | runs the pipeline at 6 AM and 6 PM Eastern, builds PDFs, commits the database |

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

## Your saved links
Open **🔗 My job links** at the top of the website, paste a search link and press **Add**. Set your keywords, location
and filters on the job site first, then copy the address bar. **Test** shows the jobs on a link right away. At each
scan every job on every link (up to `links.max_jobs_per_link`) is pulled out, labelled with its website and scored.
Jobs from your links skip the job-title and location filters (your link already chose them), and low matches are
still listed as "Low match" instead of being dropped.

| Website | How it's read | Example link |
|---|---|---|
| LinkedIn | public job list + each description | `linkedin.com/jobs/search/?keywords=data%20engineer&location=Remote&f_TPR=r86400` |
| Dice | public search pages + each job page | `dice.com/jobs?q=data%20engineer&location=United%20States` |
| Indeed | search words from your link, through JobSpy | `indeed.com/jobs?q=data+engineer&l=Remote&fromage=1` |
| Wellfound | public role pages | `wellfound.com/role/data-engineer` or `wellfound.com/role/l/data-engineer/remote` |
| Handshake | **not possible**: needs your school sign-in. Turn on its job-alert emails. | |

On Streamlit Cloud the website can't keep files, so add two secrets (**App settings → Secrets**) to make **Add** and
**Remove** save `links.yml` to GitHub, and to show a **Scan my links now** button:
```
GITHUB_TOKEN = "github_pat_..."   # fine-grained token, this repo only: Contents read/write + Actions read/write
GITHUB_REPO = "SRIIAKHILLESSH/job-application"
```
Without them, edit `links.yml` in GitHub directly.

## Sources not covered
Handshake only shows jobs to signed-in students, so it isn't scraped. LinkedIn sometimes withholds full
descriptions (rate limit); those jobs are listed as "No description" and not scored.

## Run locally
```
python -m venv .venv && .venv/Scripts/python -m pip install -r requirements.txt
.venv/Scripts/python -m pytest -q
.venv/Scripts/python -m jobapp.run --dry-run        # counts only
.venv/Scripts/python -m jobapp.run                  # writes data/ and resumes/
.venv/Scripts/streamlit run app.py
```
