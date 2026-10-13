from datetime import date

from jobapp import ats, filters, resume, skills
from jobapp.run import load_config, process

CFG = load_config()
MASTER = resume.load_master()


def _job(title, desc, location="Remote - US", posted="", source="greenhouse", company="Acme"):
    return {"id": title[:10], "source": source, "company": company, "title": title, "location": location,
            "url": f"https://x/{title}", "posted": posted, "description": desc, "remote": None}


def test_skill_matching_is_whole_token():
    c = skills.counts("PySpark and Spark SQL on GitHub; JavaScript")
    assert c["PySpark"] == 1 and c["Spark SQL"] == 1 and c["GitHub"] == 1 and c["JavaScript"] == 1
    assert "Git" not in c and "Java" not in c


def test_title_families_and_exclusions():
    assert filters.family("Data Engineer II", CFG) == "data"
    assert filters.family("Senior DevOps Engineer", CFG) == "devops"
    assert filters.family("Staff Data Engineer", CFG) is None
    assert filters.family("Engineering Manager, Data", CFG) is None
    assert filters.family("Account Executive", CFG) is None


def test_location_filter():
    assert filters.us_or_remote("Austin, TX", None)
    assert filters.us_or_remote("Remote - US", None)
    assert filters.us_or_remote("San Francisco, CA | New York, NY", None)
    assert not filters.us_or_remote("London, UK", None)
    assert not filters.us_or_remote("Bengaluru, Karnataka, IN", None)
    assert not filters.us_or_remote("Remote - Canada", True)


def test_fresh():
    assert filters.fresh("2026-10-01", 30, date(2026, 10, 13))
    assert not filters.fresh("2026-08-01", 30, date(2026, 10, 13))
    assert filters.fresh("", 30, date(2026, 10, 13))


def test_ats_score_and_flags():
    s = ats.score("Data Engineer", "Python, SQL, Databricks and Kafka. Python again.", resume.to_text(MASTER))
    assert "Kafka" in s["missing"] and "Python" in s["matched"] and 0 < s["ats"] < 100
    assert ats.years_required("Requires 5+ years of experience with Python") == 5
    assert "clearance/citizenship" in ats.flags("Active TS/SCI clearance required")
    assert "no sponsorship" in ats.flags("We are unable to sponsor visas for this role")


def test_tailoring_never_adds_skills_without_the_bank():
    want = ats.job_keywords("DevOps Engineer", "Kubernetes, Terraform, Kafka, CI/CD, AWS " * 3)
    tex, added = resume.tailor(MASTER, "devops", want, bank=[])
    assert added == []
    assert set(skills.counts(resume.to_text(tex))) == set(skills.counts(resume.to_text(MASTER)))
    assert sorted(tex.split("\n")) != sorted(MASTER.split("\n")) or tex != MASTER  # reordered, same content
    # every bullet is still there, exactly once
    bullets = [ln.strip() for ln in MASTER.split("\n") if ln.strip().startswith(r"\resumeItem{")]
    assert sorted(ln.strip() for ln in tex.split("\n") if ln.strip().startswith(r"\resumeItem{")) == sorted(bullets)


def test_tailoring_adds_bank_skills_only_when_asked():
    want = ats.job_keywords("Data Engineer", "Kafka streaming with Python")
    tex, added = resume.tailor(MASTER, "data", want, bank=["Kafka", "Kubernetes"])
    assert added == ["Kafka"]
    assert "Kafka" in skills.counts(resume.to_text(tex)) and "Kubernetes" not in skills.counts(resume.to_text(tex))


def test_pipeline_routes_by_score():
    desc_hi = "We need Python, SQL, PySpark, Databricks, Delta Lake, Airflow, AWS, S3, Terraform and CI/CD. " * 5
    desc_mid = "Python, SQL, AWS, Terraform, Kafka, Kubernetes, dbt, Scala and Spark. " * 5
    desc_lo = "Rust, Go-lang, React, TypeScript, Kubernetes, Helm, Flink, Kafka, Scala, Java. " * 5
    jobs = [_job("Data Engineer", desc_hi, company="A"), _job("Data Engineer", desc_mid, company="B"),
            _job("DevOps Engineer", desc_lo, company="C"), _job("Data Engineer", "", source="linkedin", company="D"),
            _job("Data Engineer", desc_hi, location="London, UK", company="E")]
    out = process(jobs, CFG, set(), MASTER, [], "2026-10-13T12:00:00Z")
    dec = {r["company"]: r["decision"] for r in out["records"]}
    assert dec == {"A": "ready", "B": "tailored", "D": "no_description"}
    assert out["counts"]["not_relevant"] == 1
    # already-seen jobs are skipped on the next run
    again = process(jobs, CFG, out["seen"], MASTER, [], "2026-10-13T22:00:00Z")
    assert again["records"] == []


def test_multiword_states_are_not_split():
    assert not filters.us_or_remote("Vancouver, British Columbia", None)
    assert filters.us_or_remote("Washington, District of Columbia", None)


def test_few_keywords_are_not_a_perfect_score():
    s = ats.score("Network Engineer", "Linux and Python.", resume.to_text(MASTER))
    assert s["ats"] < 50


def test_tailoring_names_umbrella_terms_backed_by_listed_tools():
    want = ats.job_keywords("DevOps Engineer", "Infrastructure as Code, data warehouse, Kubernetes")
    tex, added = resume.tailor(MASTER, "devops", want, bank=[])
    assert set(added) == {"Infrastructure as Code", "Data Warehouse"}  # Terraform / Redshift+Snowflake are listed
    assert "Kubernetes" not in added
    before = ats.score("DevOps Engineer", "Infrastructure as Code, data warehouse, Kubernetes", resume.to_text(MASTER))
    after = ats.score("DevOps Engineer", "Infrastructure as Code, data warehouse, Kubernetes", resume.to_text(tex))
    assert after["ats"] > before["ats"]
