"""Job search dashboard: every job the scanner found, how well your resume matches, and what to apply to next."""
import html
import json
import urllib.parse
from collections import Counter
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from jobapp import store

ROOT = Path(__file__).resolve().parent
st.set_page_config(page_title="Job Search Dashboard", page_icon="💼", layout="wide")

STATUS = {"ready": "Ready (ATS ≥ 90)", "tailored": "Tailored resume", "not_tailored": "Queued for tailoring",
          "no_description": "No description"}
COLORS = {"Ready (ATS ≥ 90)": "#2e9e5b", "Tailored resume": "#3b7dd8", "Queued for tailoring": "#e3a33b",
          "No description": "#9aa0a6"}
SOURCE_NAMES = {"linkedin": "LinkedIn", "indeed": "Indeed", "greenhouse": "Greenhouse", "lever": "Lever", "ashby": "Ashby"}

st.markdown("""<style>
  .block-container {padding-top: 1.6rem; padding-bottom: 2rem;}
  div[data-testid="stMetric"] {background: rgba(127,127,127,.07); border: 1px solid rgba(127,127,127,.18);
    border-radius: 12px; padding: 12px 16px;}
  div[data-testid="stMetricValue"] {font-size: 1.7rem;}
  .chip {display:inline-block; padding:2px 9px; margin:2px 3px 2px 0; border-radius:999px; font-size:.82rem;}
  .ok {background:rgba(46,158,91,.15); color:#2e9e5b;} .miss {background:rgba(214,69,65,.13); color:#d64541;}
  .add {background:rgba(59,125,216,.15); color:#3b7dd8;}
</style>""", unsafe_allow_html=True)


@st.cache_data(ttl=300)
def load() -> pd.DataFrame:
    df = pd.DataFrame(store.load_all())
    if df.empty:
        return df
    df["found"] = pd.to_datetime(df["found_utc"]).dt.tz_localize(None)
    df["found_day"] = df["found"].dt.date
    df["status"] = df["decision"].map(STATUS)
    df["src"] = df["source"].map(SOURCE_NAMES).fillna(df["source"])
    df["flag_text"] = df["flags"].map(", ".join)
    return df.sort_values(["found", "ats_after"], ascending=[False, False]).reset_index(drop=True)


def chart(fig, h=300):
    fig.update_layout(height=h, margin=dict(l=8, r=8, t=36, b=8), legend_title_text="",
                      paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font=dict(size=12))
    st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})


def chips(items, cls):
    return " ".join(f'<span class="chip {cls}">{html.escape(i)}</span>' for i in items) or "—"


def overleaf_button(tex: str, name: str) -> None:
    """POSTs the .tex to Overleaf, which opens it as a new project (you must be signed in to Overleaf)."""
    st.iframe(f"""
      <form action="https://www.overleaf.com/docs" method="post" target="_blank" style="margin:0">
        <input type="hidden" name="encoded_snip" value="{html.escape(urllib.parse.quote(tex))}">
        <input type="hidden" name="snip_name" value="{html.escape(name)}">
        <input type="hidden" name="engine" value="pdflatex">
        <button type="submit" style="width:100%;padding:.45rem .8rem;border-radius:.5rem;border:1px solid #2e9e5b;
          background:#2e9e5b;color:white;font:500 14px sans-serif;cursor:pointer">Open in Overleaf ↗</button>
      </form>""", height=54)


df = load()
last = ROOT / "data" / "last_run.json"
run = json.loads(last.read_text()) if last.exists() else None

st.title("💼 Job Search Dashboard")
st.caption("Data / DevOps / Python jobs from LinkedIn, Indeed and company job boards, scored against your resume. "
           "ATS ≥ 90 → apply with your master resume. Below 90 → a tailored resume (same facts, reordered for the job). "
           "You apply yourself; nothing is submitted automatically.")
if df.empty:
    st.info("No jobs yet. The first scan fills this dashboard.", icon="⏳")
    st.stop()

# ---------------------------------------------------------------- filters (apply to the whole dashboard)
with st.sidebar:
    st.header("Filters")
    days = st.select_slider("Found in the last", [1, 3, 7, 14, 30, 60, 365], value=30, format_func=lambda d: f"{d} days")
    status = st.multiselect("Status", list(STATUS.values()), default=list(STATUS.values()))
    fam = st.multiselect("Role family", sorted(df.family.unique()), default=sorted(df.family.unique()),
                         format_func=str.title)
    src = st.multiselect("Source", sorted(df.src.unique()), default=sorted(df.src.unique()))
    min_ats = st.slider("Minimum ATS score", 0, 100, 0, 5)
    hide = st.checkbox("Hide clearance / no-sponsorship jobs")
    q = st.text_input("Search title or company")
    st.divider()
    if run:
        bad = {k: v for k, v in run["sources"].items() if not isinstance(v, int)}
        st.caption(f"Last scan: {run['run_utc'][:16].replace('T', ' ')} UTC  \n"
                   f"{run['counts']['fetched']:,} postings checked from {len(run['sources'])} sources"
                   + (f"  \n⚠️ {len(bad)} source(s) failed" if bad else "  \n✅ all sources OK"))
    st.caption("Scans run automatically at 8 AM and 6 PM Eastern.")

v = df[df.status.isin(status) & df.family.isin(fam) & df.src.isin(src)]
v = v[v.found >= pd.Timestamp.now(tz="UTC").tz_localize(None).normalize() - pd.Timedelta(days=days - 1)]
v = v[(v.ats_after.fillna(-1) >= min_ats) | ((min_ats == 0) & v.ats_after.isna())]
if hide:
    v = v[v["flags"].map(len) == 0]
if q:
    v = v[v.title.str.contains(q, case=False, regex=False) | v.company.str.contains(q, case=False, regex=False)]
scored = v[v.ats_after.notna()]

# ---------------------------------------------------------------- KPIs
today = pd.Timestamp.now(tz="UTC").tz_localize(None).normalize()
k = st.columns(6)
k[0].metric("Jobs in view", f"{len(v):,}", f"of {len(df):,} total", delta_color="off", delta_arrow="off")
k[1].metric("New today", int((v.found >= today).sum()))
k[2].metric("Ready (≥ 90)", int((v.decision == "ready").sum()))
k[3].metric("Tailored resumes", int((v.decision == "tailored").sum()))
k[4].metric("Average ATS", f"{scored.ats_after.mean():.0f}" if len(scored) else "—",
            f"+{(scored.ats_after - scored.ats_before).mean():.1f} from tailoring" if len(scored) else None,
            delta_color="off", delta_arrow="off")
k[5].metric("Companies", v.company.nunique())

if v.empty:
    st.warning("No jobs match these filters.")
    st.stop()

tab_dash, tab_apply, tab_all, tab_job = st.tabs(["📊 Overview", "🎯 Apply next", "📋 All jobs", "🔎 Job details"])

# ---------------------------------------------------------------- overview
with tab_dash:
    a, b = st.columns([3, 2])
    with a:
        per_day = v.groupby(["found_day", "status"]).size().reset_index(name="jobs")
        fig = px.bar(per_day, x="found_day", y="jobs", color="status", color_discrete_map=COLORS,
                     title="Jobs found per day", category_orders={"status": list(STATUS.values())})
        fig.update_xaxes(title=None, type="category" if per_day.found_day.nunique() < 4 else "date")
        fig.update_yaxes(title=None)
        fig.update_layout(legend=dict(orientation="h", y=-0.15))
        chart(fig)
    with b:
        fig = go.Figure()
        fig.add_histogram(x=scored.ats_before, name="Master resume", xbins=dict(start=50, end=100.01, size=5),
                          marker_color="#9aa0a6", opacity=.6)
        fig.add_histogram(x=scored.ats_after, name="Resume sent", xbins=dict(start=50, end=100.01, size=5),
                          marker_color="#3b7dd8", opacity=.8)
        fig.add_vline(x=90, line_dash="dash", line_color="#2e9e5b", annotation_text="90 = ready")
        fig.update_layout(barmode="overlay", title="ATS score spread", legend=dict(orientation="h", y=-0.15))
        fig.update_xaxes(title=None)
        fig.update_yaxes(title="jobs")
        chart(fig)

    a, b, c = st.columns(3)
    with a:
        s = v.groupby(["src", "status"]).size().reset_index(name="jobs")
        fig = px.bar(s, y="src", x="jobs", color="status", orientation="h", color_discrete_map=COLORS,
                     title="By source", category_orders={"status": list(STATUS.values())})
        fig.update_layout(showlegend=False)
        fig.update_yaxes(title=None, categoryorder="total ascending")
        fig.update_xaxes(title=None)
        chart(fig, 280)
    with b:
        f = v.family.str.title().value_counts().reset_index()
        fig = px.pie(f, names="family", values="count", hole=.55, title="By role family",
                     color_discrete_sequence=["#3b7dd8", "#2e9e5b", "#e3a33b"])
        fig.update_traces(textinfo="value", textposition="inside")
        fig.update_layout(legend=dict(orientation="h", y=-0.1))
        chart(fig, 280)
    with c:
        top = v.company.value_counts().head(10).sort_values().reset_index()
        fig = px.bar(top, y="company", x="count", orientation="h", title="Top hiring companies",
                     color_discrete_sequence=["#3b7dd8"])
        fig.update_yaxes(title=None)
        fig.update_xaxes(title=None)
        chart(fig, 280)

    a, b = st.columns(2)
    n = len(scored)
    with a:
        miss = Counter(m for ms in scored.missing for m in ms).most_common(12)
        if miss:
            m = pd.DataFrame(miss, columns=["skill", "jobs"]).iloc[::-1]
            m["share"] = m.jobs / n * 100
            fig = px.bar(m, y="skill", x="share", orientation="h", title="Skills jobs ask for that your resume lacks",
                         color_discrete_sequence=["#d64541"], custom_data=["jobs"])
            fig.update_traces(hovertemplate="%{y}: %{customdata[0]} jobs (%{x:.0f}%)<extra></extra>")
            fig.update_xaxes(title=f"% of {n} scored jobs", ticksuffix="%")
            fig.update_yaxes(title=None)
            chart(fig, 360)
            st.caption("Learning the top ones (or adding them to `resume/skills_bank.yml` if you already know them) "
                       "raises the most scores.")
    with b:
        hit = Counter(m for ms in scored.matched for m in ms).most_common(12)
        if hit:
            h = pd.DataFrame(hit, columns=["skill", "jobs"]).iloc[::-1]
            h["share"] = h.jobs / n * 100
            fig = px.bar(h, y="skill", x="share", orientation="h", title="Your skills employers ask for most",
                         color_discrete_sequence=["#2e9e5b"], custom_data=["jobs"])
            fig.update_traces(hovertemplate="%{y}: %{customdata[0]} jobs (%{x:.0f}%)<extra></extra>")
            fig.update_xaxes(title=f"% of {n} scored jobs", ticksuffix="%")
            fig.update_yaxes(title=None)
            chart(fig, 360)

# ---------------------------------------------------------------- apply next
with tab_apply:
    st.caption("Best matches first: highest ATS score for the resume you'd send, newest first on ties. "
               "Jobs flagged for clearance or no sponsorship are marked ⚠️.")
    best = scored.sort_values(["ats_after", "found"], ascending=[False, False]).head(15)
    for _, r in best.iterrows():
        with st.container(border=True):
            c1, c2, c3 = st.columns([5, 1.2, 1.4])
            c1.markdown(f"**{html.escape(r.title)}** · {html.escape(r.company)}  \n"
                        f"<span style='opacity:.7'>{html.escape(r.location or 'Location not given')} · {r.src} · "
                        f"posted {r.posted or '—'}{' · ⚠️ ' + r.flag_text if r.flag_text else ''}</span>",
                        unsafe_allow_html=True)
            c2.metric("ATS score", f"{r.ats_after:.0f}", f"+{r.ats_after - r.ats_before:.1f} tailored"
                      if r.ats_after > r.ats_before else None, delta_arrow="off")
            c3.link_button("Apply ↗", r.url, width="stretch")
            if r.pdf:
                c3.link_button("Resume PDF", r.pdf, width="stretch")
            c1.markdown("Missing: " + chips(r.missing[:6], "miss"), unsafe_allow_html=True)

# ---------------------------------------------------------------- all jobs
with tab_all:
    st.dataframe(
        v[["status", "ats_after", "ats_before", "company", "title", "location", "src", "posted", "url", "pdf",
           "flag_text"]].assign(missing=v.missing.map(lambda m: ", ".join(m[:4]))),
        hide_index=True, width="stretch", height=560,
        column_config={
            "status": "Status",
            "ats_after": st.column_config.ProgressColumn("ATS (resume to send)", min_value=0, max_value=100,
                                                         format="%.0f"),
            "ats_before": st.column_config.NumberColumn("ATS master", format="%.0f"),
            "company": "Company", "title": "Title", "location": "Location", "src": "Source", "posted": "Posted",
            "url": st.column_config.LinkColumn("Job", display_text="Apply ↗"),
            "pdf": st.column_config.LinkColumn("Resume", display_text="PDF ↗"),
            "flag_text": "Flags", "missing": "Missing keywords",
        })
    st.download_button("Download this list (CSV)",
                       v.drop(columns=["description"], errors="ignore").to_csv(index=False),
                       file_name="jobs.csv", mime="text/csv")

# ---------------------------------------------------------------- one job
with tab_job:
    labels = {i: f"{r.company} · {r.title} · ATS {r.ats_after:.0f}" if pd.notna(r.ats_after)
              else f"{r.company} · {r.title} · not scored" for i, r in v.iterrows()}
    i = st.selectbox("Pick a job", list(labels), format_func=labels.get)
    r = v.loc[i]
    a, b = st.columns([2.2, 1])
    with a:
        st.markdown(f"### {html.escape(r.title)}\n**{html.escape(r.company)}** · {html.escape(r.location or '—')} · "
                    f"{r.src} · posted {r.posted or '—'} · {r.status}")
        if r.decision == "no_description":
            st.warning("The source didn't give a description, so this job wasn't scored. Open the link to read it.")
        else:
            g = st.columns(3)
            g[0].metric("ATS with master resume", f"{r.ats_before:.0f}")
            g[1].metric("ATS with resume to send", f"{r.ats_after:.0f}", f"{r.ats_after - r.ats_before:+.1f}")
            g[2].metric("Skills in the job", int(r.get("n_keywords") or 0))
            st.markdown("**Matched:** " + chips(r.matched, "ok"), unsafe_allow_html=True)
            st.markdown("**Missing:** " + chips(r.missing, "miss"), unsafe_allow_html=True)
            if r.added_skills:
                st.markdown("**Added to the tailored resume:** " + chips(r.added_skills, "add"), unsafe_allow_html=True)
        if r["flags"]:
            st.error("Check before applying: " + r.flag_text)
        if pd.notna(r.get("years_required")):
            st.caption(f"Asks for about {int(r.years_required)}+ years of experience.")
    with b:
        st.link_button("Open job posting ↗", r.url, width="stretch", type="primary")
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
