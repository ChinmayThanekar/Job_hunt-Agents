#!/usr/bin/env python3
"""
ATS Resume, Cover Letter & Screening Answers Tailor Agent Script.
Uses Google Gemini (gemini-2.5-pro / gemini-2.5-flash) to tailor profile/base_resume.md
for high-match jobs without fabricating credentials.
"""

import argparse
import json
import re
from pathlib import Path
from typing import Any, Dict

from gemini_client import call_gemini, extract_json, load_base_resume, load_profile
from tracker import get_conn, init_db

ROOT_DIR = Path(__file__).resolve().parent.parent
APPS_DIR = ROOT_DIR / "applications"


def slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")


def tailor_for_job(job: Dict[str, Any], profile: Dict[str, Any], base_resume: str) -> Path:
    company_slug = slugify(job["company"])
    out_dir = APPS_DIR / f"{company_slug}_{job['id']}"
    out_dir.mkdir(parents=True, exist_ok=True)

    autonomy = profile.get("autonomy_settings", {})
    model = autonomy.get("tailoring_model", "gemini-2.5-pro")
    candidate = profile.get("candidate", {})
    skills = profile.get("skills", {})
    highlights = profile.get("highlight_achievements", [])

    prompt = f"""
You are an expert ATS Resume & Application Strategist.
Tailor the candidate's base resume and application materials for the target job below.
STRICT RULE: Do NOT fabricate employers, job titles, degrees, or skills the candidate does not possess.

TARGET JOB:
Company: {job['company']}
Title: {job['title']}
Location: {job.get('location', '')}
Job Description:
{job.get('description', '')[:3500]}

CANDIDATE PROFILE:
{json.dumps(profile, indent=2)}

BASE RESUME:
{base_resume}

Return a JSON object with these exact keys:
1. "tailored_resume_md": Full tailored Markdown resume optimized for ATS keyword alignment with this job.
2. "cover_letter_md": Concise (<220 words), high-converting cover letter tailored to {job['company']} and {job['title']}.
3. "screening_answers": Object with keys:
   - "why_company": 2-3 sentence answer to "Why do you want to work at {job['company']}?"
   - "relevant_project": 3-4 sentence answer describing the most relevant engineering achievement.
   - "work_authorization": "{candidate.get('work_authorization', 'Authorized to work')}"
   - "notice_period_days": "{candidate.get('notice_period_days', 15)}"
4. "ats_keywords_matched": List of key terms from the JD included in the tailored resume.
"""
    raw = call_gemini(prompt, model=model, json_output=True)
    parsed = extract_json(raw or "")

    # Fallback deterministic tailoring if Gemini key is not yet configured
    jd_text = (job.get("description") or "") + " " + job["title"]
    all_skills = skills.get("primary", []) + skills.get("secondary", [])
    matched_kw = [s for s in all_skills if s.lower() in jd_text.lower()] or skills.get("primary", [])[:6]

    tailored_resume_md = parsed.get("tailored_resume_md") or (
        f"<!-- Tailored for {job['company']} - {job['title']} (ATS Keywords: {', '.join(matched_kw)}) -->\n"
        + base_resume
    )
    cover_letter_md = parsed.get("cover_letter_md") or (
        f"Dear Hiring Team at {job['company']},\n\n"
        f"I am excited to apply for the **{job['title']}** position at **{job['company']}**. "
        f"With {candidate.get('years_of_experience', 3)}+ years of experience building scalable production systems "
        f"using {', '.join(matched_kw[:5])}, I have consistently delivered high-reliability backend and AI workflows.\n\n"
        f"Key highlights relevant to this role:\n"
        + "\n".join(f"- {h}" for h in highlights[:3])
        + f"\n\nI would welcome the opportunity to discuss how my background aligns with {job['company']}'s engineering goals.\n\n"
        f"Best regards,\n{candidate.get('full_name', 'Candidate')}\n"
        f"{candidate.get('email', '')} | {candidate.get('linkedin_url', '')}\n"
    )
    screening_answers = parsed.get("screening_answers") or {
        "why_company": (
            f"I've followed {job['company']}'s engineering impact closely and want to bring my experience in "
            f"{', '.join(matched_kw[:4])} to help scale the {job['title']} initiatives."
        ),
        "relevant_project": highlights[0] if highlights else "Built and scaled high-throughput production APIs and agentic systems.",
        "work_authorization": candidate.get("work_authorization", "Authorized"),
        "notice_period_days": str(candidate.get("notice_period_days", 15)),
    }
    ats_analysis = {
        "job_id": job["id"],
        "company": job["company"],
        "title": job["title"],
        "matched_keywords": parsed.get("ats_keywords_matched") or matched_kw,
    }

    (out_dir / "tailored_resume.md").write_text(tailored_resume_md, encoding="utf-8")
    (out_dir / "cover_letter.md").write_text(cover_letter_md, encoding="utf-8")
    (out_dir / "screening_answers.json").write_text(json.dumps(screening_answers, indent=2), encoding="utf-8")
    (out_dir / "ats_analysis.json").write_text(json.dumps(ats_analysis, indent=2), encoding="utf-8")

    with get_conn() as conn:
        conn.execute(
            "UPDATE jobs SET tailored_dir = ? WHERE id = ?",
            (str(out_dir), job["id"]),
        )
    return out_dir


def main() -> None:
    parser = argparse.ArgumentParser(description="Tailor resume, cover letter, and screening answers")
    parser.add_argument("--job-id", type=int, default=None, help="Specific job ID to tailor")
    parser.add_argument("--all-ready", action="store_true", help="Tailor all jobs in READY_TO_AUTO_APPLY status")
    args = parser.parse_args()

    init_db()
    profile = load_profile()
    base_resume = load_base_resume()

    with get_conn() as conn:
        if args.job_id is not None:
            jobs = [dict(r) for r in conn.execute("SELECT * FROM jobs WHERE id = ?", (args.job_id,)).fetchall()]
        elif args.all_ready:
            jobs = [
                dict(r)
                for r in conn.execute(
                    "SELECT * FROM jobs WHERE status = 'READY_TO_AUTO_APPLY' OR match_score >= 80"
                ).fetchall()
            ]
        else:
            raise SystemExit("Specify --job-id <ID> or --all-ready")

    tailored = []
    for job in jobs:
        out_dir = tailor_for_job(job, profile, base_resume)
        tailored.append({"job_id": job["id"], "company": job["company"], "title": job["title"], "tailored_dir": str(out_dir)})

    print(json.dumps({"tailored_count": len(tailored), "packages": tailored}, indent=2))


if __name__ == "__main__":
    main()
