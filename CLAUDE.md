# AI Job Application

Job scanner + ATS check + resume tailoring + job links website. See README.md for the layout.

## How to work here
1. `git pull --ff-only` first. The "Scan jobs" GitHub Action commits `data/` and `resumes/` twice a day.
2. Python: `.venv/Scripts/python` (local), 3.12 in Actions. Tests: `.venv/Scripts/python -m pytest -q`; website smoke test with `streamlit.testing.v1.AppTest` on `app.py`.
3. Commit with a clear message and push; Streamlit Cloud redeploys `app.py` from `main`.

## Ground rules
- Tailoring may only reorder, re-label, or add skills from `resume/skills_bank.yml`. Never invent skills, experience,
  numbers or titles, and never add hidden/white text to game an ATS.
- Never submit applications, log into job sites, or handle the user's passwords. Handshake, Wellfound and Dice
  need sign-in and are out of scope.
- `data/jobs/*.jsonl` is append-only; don't rewrite or delete it. Don't force-push.
- The resume contains personal contact details; don't publish it anywhere new.
