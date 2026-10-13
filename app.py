"""Job links database: every relevant job the scanner found, its ATS score, and the resume to send."""
import html
import json
import urllib.parse
from pathlib import Path

import pandas as pd
import streamlit as st

from jobapp import store

ROOT = Path(__file__).resolve().parent
st.set_page_config(page_title="AI Job Application", page_icon="💼", layout="wide")

DECISIONS = {"ready": "✅ Ready (ATS ≥ 90)", "tailored": "✏️ Tailored resume", "not_tailored": "⏸️ Not tailored yet",
             "no_description": "❔ No description"}


@st.cache_data(ttl=300)
def load() -> pd.DataFrame:
    df = pd.DataFrame(store.load_all())
    if df.empty:
        return df
    df["found"] = pd.to_datetime(df["found_utc"]).dt.tz_localize(None)
    df["gain"] = df["ats_after"] - df["ats_before"]
    return df.sort_values(["found", "ats_after"], ascending=[False, False]).reset_index(drop=True)


def overleaf_button(tex: str, name: str) -> None:
    """POSTs the .tex to Overleaf, which opens it as a new project (you must be signed in to Overleaf)."""
    st.iframe(f"""
      <form action="https://www.overleaf.com/docs" method="post" target="_blank" style="margin:0">
        <input type="hidden" name="encoded_snip" value="{html.escape(urllib.parse.quote(tex))}">
        <input type="hidden" name="snip_name" value="{html.escape(name)}">
        <input type="hidden" name="engine" value="pdflatex">
        <button type="submit" style="width:100%;padding:.45rem .8rem;border-radius:.5rem;border:1px solid #4f9a6b;
          background:#4f9a6b;color:white;font:500 14px sans-serif;cursor:pointer">Open in Overleaf ↗</button>
      </form>""", height=44)


st.title("💼 AI Job Application")
st.caption("Jobs scraped from LinkedIn, Indeed and company job boards (Greenhouse, Lever, Ashby), scored against your "
           "resume. ATS ≥ 90 → ready with your master resume; below 90 → a tailored resume (same facts, reordered "
           "for the job). You apply yourself; nothing is submitted automatically.")

df = load()
last = ROOT / "data" / "last_run.json"
run = json.loads(last.read_text()) if last.exists() else None
if df.empty:
    st.info("No jobs yet. The first cloud run fills this page.", icon="⏳")
    st.stop()

# ---------------------------------------------------------------- filters
with st.sidebar:
    st.header("Filter")
    dec = st.multiselect("Status", list(DECISIONS), default=["ready", "tailored"], format_func=DECISIONS.get)
    fam = st.multiselect("Role family", sorted(df.family.unique()), default=sorted(df.family.unique()))
    src = st.multiselect("Source", sorted(df.source.unique()), default=sorted(df.source.unique()))
    min_ats = st.slider("Minimum ATS score (after tailoring)", 0, 100, 0, 5)
    days = st.slider("Found in the last N days", 1, 60, 14)
    hide = st.checkbox("Hide clearance / citizenship / no-sponsorship jobs", value=False)
    q = st.text_input("Search title or company")

v = df[df.decision.isin(dec) & df.family.isin(fam) & df.source.isin(src)]
v = v[(v.ats_after.fillna(0) >= min_ats) | v.ats_after.isna() & (min_ats == 0)]
v = v[v.found >= pd.Timestamp.now(tz="UTC").tz_localize(None) - pd.Timedelta(days=days)]
if hide:
    v = v[v["flags"].map(len) == 0]
if q:
    v = v[v.title.str.contains(q, case=False) | v.company.str.contains(q, case=False)]

c = st.columns(4)
c[0].metric("Jobs in database", len(df))
c[1].metric("Ready (ATS ≥ 90)", int((df.decision == "ready").sum()))
c[2].metric("Tailored resumes", int((df.decision == "tailored").sum()))
c[3].metric("Last scan (UTC)", run["run_utc"][:16].replace("T", " ") if run else "—",
            f"+{run['counts']['ready'] + run['counts']['tailored']} new" if run else None, delta_color="off")

# ---------------------------------------------------------------- table
st.subheader(f"{len(v)} jobs")
table = v.assign(status=v.decision.map(DECISIONS), flag=v["flags"].map(", ".join),
                 missing_top=v.missing.map(lambda m: ", ".join(m[:4])))
st.dataframe(
    table[["status", "ats_after", "ats_before", "company", "title", "location", "source", "posted", "url", "pdf",
           "missing_top", "flag"]],
    hide_index=True, width="stretch", height=480,
    column_config={
        "status": "Status",
        "ats_after": st.column_config.ProgressColumn("ATS (resume to send)", min_value=0, max_value=100, format="%.0f"),
        "ats_before": st.column_config.NumberColumn("ATS master", format="%.0f"),
        "url": st.column_config.LinkColumn("Job link", display_text="Apply ↗"),
        "pdf": st.column_config.LinkColumn("Resume PDF", display_text="PDF ↗"),
        "missing_top": "Missing keywords",
        "flag": "Flags",
    })

# ---------------------------------------------------------------- one job
st.subheader("Job details")
if len(v):
    labels = {i: f"{r.company} · {r.title} · ATS {r.ats_after if pd.notna(r.ats_after) else '—'}" for i, r in v.iterrows()}
    i = st.selectbox("Pick a job", list(labels), format_func=labels.get)
    r = v.loc[i]
    a, b = st.columns([2, 1])
    with a:
        st.markdown(f"### {r.title}\n**{r.company}** · {r.location or 'location not given'} · {r.source} · "
                    f"posted {r.posted or '—'}")
        if r.decision == "no_description":
            st.warning("The source didn't give a description, so this job wasn't scored. Open the link to read it.")
        else:
            st.markdown(f"**ATS score:** master resume {r.ats_before:.0f} → resume to send **{r.ats_after:.0f}**")
            st.markdown("**Matched:** " + (", ".join(f"`{m}`" for m in r.matched) or "—"))
            st.markdown("**Missing:** " + (", ".join(f"`{m}`" for m in r.missing) or "nothing"))
            if r.added_skills:
                st.markdown("**Added from your skills bank:** " + ", ".join(r.added_skills))
        if r["flags"]:
            st.error("Check before applying: " + ", ".join(r["flags"]))
        if isinstance(r.get("years_required"), (int, float)) and pd.notna(r.years_required):
            st.caption(f"Asks for about {int(r.years_required)}+ years of experience.")
    with b:
        st.link_button("Open job posting ↗", r.url, width="stretch")
        if r.pdf:
            st.link_button("Download resume PDF ↗", r.pdf, width="stretch")
        tex_path = ROOT / (r.resume or "resume/master.tex")
        if tex_path.exists():
            tex = tex_path.read_text(encoding="utf-8")
            name = f"{r.company}_{r.title}"[:60].replace(" ", "_").replace("/", "-") + ".tex"
            st.download_button("Download .tex", tex, file_name=name, width="stretch")
            overleaf_button(tex, name)
    if r.description:
        with st.expander("Job description"):
            st.markdown(r.description)

if run:
    with st.expander("Last scan details"):
        st.json(run["counts"])
        bad = {k: v for k, v in run["sources"].items() if not isinstance(v, int)}
        st.write(f"{len(run['sources'])} sources checked" + (f"; {len(bad)} failed: {bad}" if bad else ", all OK."))
