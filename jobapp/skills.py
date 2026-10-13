"""Skill vocabulary used to read job descriptions and the resume the way an ATS keyword filter does.

Each entry: canonical name -> (resume skills category, regex alternatives). Matching is case-insensitive and
whole-token (so "spark" does not match inside "pyspark", and "git" does not match "github").
"""
from __future__ import annotations

import re
from collections import Counter

PROG, DATA, CLOUD, WEB = "Programming", "Data Engineering", "Cloud & DevOps", "Web & Databases"

VOCAB: dict[str, tuple[str, list[str]]] = {
    # languages
    "Python": (PROG, [r"python"]),
    "SQL": (PROG, [r"sql"]),
    "PySpark": (PROG, [r"pyspark"]),
    "Spark SQL": (PROG, [r"spark sql", r"sparksql"]),
    "Scala": (PROG, [r"scala"]),
    "Java": (PROG, [r"java"]),
    "Bash": (PROG, [r"bash", r"shell scripting", r"shell scripts?"]),
    "PowerShell": (PROG, [r"powershell"]),
    "Pandas": (PROG, [r"pandas"]),
    "NumPy": (PROG, [r"numpy"]),
    "JavaScript": (PROG, [r"javascript", r"js"]),
    "TypeScript": (PROG, [r"typescript"]),
    "Go": (PROG, [r"golang"]),
    "Rust": (PROG, [r"rust"]),
    "C#": (PROG, [r"c#", r"\.net"]),
    "R": (PROG, [r"r programming", r"r language"]),
    # data engineering
    "ETL": (DATA, [r"etl"]),
    "ELT": (DATA, [r"elt"]),
    "Data Pipelines": (DATA, [r"data pipelines?", r"pipelines?"]),
    "Databricks": (DATA, [r"databricks"]),
    "Apache Spark": (DATA, [r"apache spark", r"spark"]),
    "Delta Lake": (DATA, [r"delta lake", r"delta tables?"]),
    "Auto Loader": (DATA, [r"auto ?loader"]),
    "Lakehouse": (DATA, [r"lakehouse", r"medallion"]),
    "Airflow": (DATA, [r"airflow", r"mwaa"]),
    "dbt": (DATA, [r"dbt"]),
    "Kafka": (DATA, [r"kafka"]),
    "Flink": (DATA, [r"flink"]),
    "Hadoop": (DATA, [r"hadoop", r"hdfs"]),
    "Hive": (DATA, [r"hive"]),
    "Iceberg": (DATA, [r"iceberg"]),
    "Parquet": (DATA, [r"parquet"]),
    "Data Validation": (DATA, [r"data validation", r"data quality", r"reconciliation"]),
    "Data Modeling": (DATA, [r"data modell?ing", r"dimensional model(l?ing)?", r"star schema"]),
    "Data Warehouse": (DATA, [r"data warehous(e|es|ing)"]),
    "Data Lake": (DATA, [r"data lakes?"]),
    "Streaming": (DATA, [r"streaming", r"real[- ]time data"]),
    "Batch Processing": (DATA, [r"batch processing", r"batch jobs?"]),
    "Fivetran": (DATA, [r"fivetran"]),
    "Informatica": (DATA, [r"informatica"]),
    "SSIS": (DATA, [r"ssis"]),
    "Azure Data Factory": (DATA, [r"azure data factory", r"adf"]),
    "Unity Catalog": (DATA, [r"unity catalog"]),
    "Data Governance": (DATA, [r"data governance"]),
    "Tableau": (DATA, [r"tableau"]),
    "Power BI": (DATA, [r"power ?bi"]),
    "Looker": (DATA, [r"looker"]),
    "Machine Learning": (DATA, [r"machine learning"]),
    # cloud & devops
    "AWS": (CLOUD, [r"aws", r"amazon web services"]),
    "S3": (CLOUD, [r"s3"]),
    "Glue": (CLOUD, [r"aws glue", r"glue"]),
    "Lambda": (CLOUD, [r"aws lambda", r"lambda"]),
    "Redshift": (CLOUD, [r"redshift"]),
    "IAM": (CLOUD, [r"iam"]),
    "CloudWatch": (CLOUD, [r"cloudwatch"]),
    "EMR": (CLOUD, [r"emr"]),
    "Kinesis": (CLOUD, [r"kinesis"]),
    "EC2": (CLOUD, [r"ec2"]),
    "Azure": (CLOUD, [r"azure"]),
    "GCP": (CLOUD, [r"gcp", r"google cloud"]),
    "BigQuery": (CLOUD, [r"bigquery"]),
    "Terraform": (CLOUD, [r"terraform"]),
    "CloudFormation": (CLOUD, [r"cloudformation"]),
    "Ansible": (CLOUD, [r"ansible"]),
    "Jenkins": (CLOUD, [r"jenkins"]),
    "GitHub Actions": (CLOUD, [r"github actions"]),
    "Docker": (CLOUD, [r"docker", r"containers?"]),
    "Kubernetes": (CLOUD, [r"kubernetes", r"k8s", r"eks", r"aks", r"gke"]),
    "Helm": (CLOUD, [r"helm"]),
    "Git": (CLOUD, [r"git"]),
    "GitHub": (CLOUD, [r"github"]),
    "CI/CD": (CLOUD, [r"ci ?/ ?cd", r"continuous integration", r"continuous delivery", r"continuous deployment"]),
    "Infrastructure as Code": (CLOUD, [r"infrastructure as code", r"iac"]),
    "Linux": (CLOUD, [r"linux", r"unix"]),
    "Monitoring": (CLOUD, [r"monitoring", r"observability", r"alerting"]),
    "Prometheus": (CLOUD, [r"prometheus"]),
    "Grafana": (CLOUD, [r"grafana"]),
    "Datadog": (CLOUD, [r"datadog"]),
    "Splunk": (CLOUD, [r"splunk"]),
    "Secrets Management": (CLOUD, [r"secrets? management", r"vault"]),
    "Encryption": (CLOUD, [r"encryption"]),
    # web & databases
    "REST APIs": (WEB, [r"rest(ful)? apis?", r"apis?"]),
    "HTML": (WEB, [r"html"]),
    "CSS": (WEB, [r"css"]),
    "PostgreSQL": (WEB, [r"postgres(ql)?"]),
    "MySQL": (WEB, [r"mysql"]),
    "SQL Server": (WEB, [r"sql server", r"mssql", r"t-sql"]),
    "Oracle": (WEB, [r"oracle"]),
    "Snowflake": (WEB, [r"snowflake", r"snowpro"]),
    "Greenplum": (WEB, [r"greenplum"]),
    "MongoDB": (WEB, [r"mongo(db)?"]),
    "DynamoDB": (WEB, [r"dynamodb"]),
    "NoSQL": (WEB, [r"nosql"]),
    "Redis": (WEB, [r"redis"]),
    "Elasticsearch": (WEB, [r"elasticsearch", r"opensearch"]),
    "FastAPI": (WEB, [r"fastapi"]),
    "Flask": (WEB, [r"flask"]),
    "Django": (WEB, [r"django"]),
    "React": (WEB, [r"react(\.js|js)?"]),
    "Node.js": (WEB, [r"node(\.js|js)"]),
}

_EDGE_L, _EDGE_R = r"(?<![A-Za-z0-9+#/])", r"(?![A-Za-z0-9+#])"
PATTERNS = {name: re.compile(_EDGE_L + "(?:" + "|".join(alts) + ")" + _EDGE_R, re.I) for name, (_, alts) in VOCAB.items()}


def counts(text: str) -> Counter:
    """How many times each vocabulary skill appears in the text."""
    return Counter({name: n for name, p in PATTERNS.items() if (n := len(p.findall(text or "")))})


def category(name: str) -> str:
    return VOCAB[name][0]
