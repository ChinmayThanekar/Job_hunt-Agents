#!/usr/bin/env python3
"""
Pure-Python ATS-Friendly 1-Page PDF Resume Generator for Chinmay Thanekar.
Generates a valid, standard PDF-1.4 document using Helvetica / Helvetica-Bold
fonts with zero external library dependencies, so every HR outreach email has
'Chinmay_Thanekar_Data_Engineer_Resume.pdf' attached.
"""

import textwrap
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_PDF_PATH = ROOT_DIR / "profile" / "Chinmay_Thanekar_Data_Engineer_Resume.pdf"


def _pdf_escape(text: str) -> str:
    # Replace unicode bullets/dashes with standard ASCII/WinAnsi equivalents
    text = (
        text.replace("•", "-")
        .replace("–", "-")
        .replace("—", "-")
        .replace("’", "'")
        .replace("“", '"')
        .replace("”", '"')
    )
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _load_candidate() -> dict:
    try:
        from gemini_client import load_profile

        return load_profile().get("candidate", {}) or {}
    except Exception:
        return {}


def _strip_scheme(url: str) -> str:
    url = str(url or "")
    for prefix in ("https://www.", "http://www.", "https://", "http://"):
        if url.startswith(prefix):
            return url[len(prefix):]
    return url


def build_resume_pdf(output_path: Path = DEFAULT_PDF_PATH) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Page geometry: A4 (595.28 x 841.89 pt)
    commands = []
    y = 805.0
    left = 36.0

    def draw_line(text: str, font: str = "F1", size: float = 9.0, leading: float = 11.5, indent: float = 0.0) -> None:
        nonlocal y
        esc = _pdf_escape(text)
        commands.append(f"BT /{font} {size:.1f} Tf {left + indent:.1f} {y:.1f} Td ({esc}) Tj ET")
        y -= leading

    def draw_rule() -> None:
        nonlocal y
        y += 3.0
        commands.append(f"0.6 w {left:.1f} {y:.1f} m 559.0 {y:.1f} l S")
        y -= 10.0

    def draw_wrapped(text: str, font: str = "F1", size: float = 8.6, leading: float = 10.6, width: int = 106, indent: float = 0.0, bullet: bool = False) -> None:
        lines = textwrap.wrap(text, width=width)
        for idx, line in enumerate(lines):
            prefix = "- " if (bullet and idx == 0) else ("  " if bullet else "")
            draw_line(prefix + line, font=font, size=size, leading=leading, indent=indent)

    # Header (contact details are read from profile/candidate_profile.yaml, which is not committed to git)
    cand = _load_candidate()
    contact_bits = [
        cand.get("location", ""),
        cand.get("phone", ""),
        cand.get("email", ""),
        _strip_scheme(cand.get("linkedin_url", "")),
        _strip_scheme(cand.get("github_url", "")),
    ]
    draw_line(str(cand.get("full_name", "")).upper(), font="F2", size=15.0, leading=16.0)
    draw_line("Data Engineer | Spark, PySpark, Python, SQL, AWS, Databricks, Airflow", font="F2", size=9.8, leading=12.5)
    draw_line(
        " | ".join(str(b) for b in contact_bits if b),
        font="F1",
        size=8.5,
        leading=12.0,
    )
    draw_rule()

    # Summary
    draw_line("SUMMARY", font="F2", size=10.0, leading=11.5)
    draw_wrapped(
        "Data Engineer with 4+ years building production batch and event-driven data pipelines on big data and cloud platforms "
        "using Spark/PySpark, Python, Unix (Bash) scripting and advanced SQL. Cut a 2-million-row Oracle extraction from 2 hours "
        "to 3 minutes (40x) by redesigning it with JDBC partitioning, and cut warehouse query runtime by 30-50% through execution-plan "
        "tuning. Experienced with Hadoop, Hive, Databricks, Delta Lake, EMR and Airflow, and with data governance, data quality and "
        "least-privilege security controls for regulated data (GxP, legal hold, retention). Works in an onsite-offshore delivery model "
        "and presents to management. Published a 60x-cited ML paper on a face recognition-based attendance system (2023).",
        size=8.5,
        leading=10.4,
        width=110,
    )
    y -= 3.0
    draw_rule()

    # Skills
    draw_line("TECHNICAL SKILLS", font="F2", size=10.0, leading=11.5)
    skills_rows = [
        "Big Data & Processing: Apache Spark, PySpark, Hadoop, Hive, Databricks, Delta Lake, AWS EMR",
        "Languages & Scripting: Python, PySpark, SQL, HiveQL, Unix scripting (Bash)",
        "AWS Cloud: S3, Glue (Jobs, Data Catalog, Crawlers), Step Functions, Lambda, Athena, EC2, EMR, Redshift, Redshift Spectrum, IAM, CloudWatch, CloudFormation",
        "Data Engineering: ETL/ELT, batch & event-driven pipelines, data warehousing, dimensional modelling, reusable JDBC ingestion frameworks, partitioning, query optimization, data governance & quality",
        "Orchestration, DBs & DevOps: Apache Airflow, Informatica PowerCenter, Talend; Oracle, MySQL, SQL Server, PostgreSQL, Redshift, Teradata; Git, Jenkins CI/CD, CloudFormation (IaC), Docker",
    ]
    for s in skills_rows:
        draw_wrapped(s, size=8.4, leading=10.2, width=112, bullet=True)
    y -= 3.0
    draw_rule()

    # Experience
    draw_line("PROFESSIONAL EXPERIENCE", font="F2", size=10.0, leading=11.5)
    draw_line("Cognizant Technology Solutions India Pvt Ltd, Pune, India — Data Engineer, Associate (July 2022 - Present)", font="F2", size=9.0, leading=11.5)
    bullets = [
        "Delivered 10-20 curated, analytics-ready datasets (1-5 million rows per batch) to 3-5 downstream consumers by building batch ETL/ELT pipelines in PySpark on AWS EMR and Informatica PowerCenter and Python (Pandas, NumPy) ingestion into AWS (S3, Glue, Redshift) and Azure.",
        "Maintained data consistency across 27 enterprise applications by processing large-scale data with Apache Spark on Databricks and Delta Lake.",
        "Cut extraction time for a 2-million-row Oracle dataset from 2 hours to 3 minutes (40x) and improved pipeline SLA compliance by redesigning the extraction with configurable JDBC partitioning for parallel retrieval.",
        "Enabled multiple client onboarding projects to load data from Oracle, MySQL and SQL Server into AWS S3 over JDBC with zero code changes by building a configuration-driven ingestion (hydration) framework.",
        "Cut query runtime by 30-50% on warehouse workloads by writing advanced SQL and stored procedures in Redshift, Oracle, MySQL and SQL Server and tuning them through execution-plan analysis.",
        "Met GxP, legal-hold and retention requirements across 10-20 regulated pipelines by designing data governance frameworks, data quality validation rules, and least-privilege IAM roles for Lambda, Glue and EMR.",
        "Improved pipeline reliability and cut manual intervention by 20% by orchestrating ETL workflows in Apache Airflow with error handling, retry logic, dependency management and alerting.",
        "Saved 10-15 hours of manual work per week by automating ingestion and ETL workflows with AWS Lambda, Step Functions and Glue jobs.",
        "Cut production issue diagnosis time from 60-90 minutes to 20-30 minutes with CloudWatch monitoring, custom logging/alerting, and metadata/lineage tracking.",
        "Cut release time from 90 minutes to 30 minutes by provisioning pipeline resources with CloudFormation and automating testing/deployment through Jenkins CI/CD.",
    ]
    for b in bullets:
        draw_wrapped(b, size=8.3, leading=10.0, width=110, bullet=True)
    y -= 3.0
    draw_rule()

    # Education, Publications & Certifications
    draw_line("EDUCATION, PUBLICATIONS & CERTIFICATIONS", font="F2", size=10.0, leading=11.5)
    draw_line("- B.E. Electronics & Telecommunication Engineering | Yeshwantrao Chavan College of Engineering, Nagpur (2018 - 2022)", font="F1", size=8.5, leading=10.8)
    draw_line("- Publication: Face Recognition-Based Attendance System (April 2023) | Cited 60 times on Google Scholar", font="F1", size=8.5, leading=10.8)
    draw_line("- Certification: AWS Certified Cloud Practitioner", font="F1", size=8.5, leading=10.8)

    stream_data = "\n".join(commands).encode("latin-1", errors="replace")

    objects = []
    objects.append(b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n")
    objects.append(b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n")
    objects.append(
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595.28 841.89] "
        b"/Resources << /Font << /F1 4 0 R /F2 5 0 R >> >> /Contents 6 0 R >>\nendobj\n"
    )
    objects.append(b"4 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>\nendobj\n")
    objects.append(b"5 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>\nendobj\n")
    objects.append(
        f"6 0 obj\n<< /Length {len(stream_data)} >>\nstream\n".encode("ascii")
        + stream_data
        + b"\nendstream\nendobj\n"
    )

    pdf = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for obj in objects:
        offsets.append(len(pdf))
        pdf.extend(obj)

    xref_offset = len(pdf)
    pdf.extend(f"xref\n0 {len(offsets)}\n0000000000 65535 f \n".encode("ascii"))
    for off in offsets[1:]:
        pdf.extend(f"{off:010d} 00000 n \n".encode("ascii"))
    pdf.extend(
        f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n".encode("ascii")
    )

    output_path.write_bytes(bytes(pdf))
    return output_path


if __name__ == "__main__":
    p = build_resume_pdf()
    print(f"Generated PDF resume: {p} ({p.stat().st_size} bytes)")
