#!/usr/bin/env python3
"""
Multi-Platform Job Scout & Gemini Match Scorer.
Fetches open roles from Greenhouse, Lever, Ashby, and public remote boards,
scores each role (0-100%) using Google Gemini (gemini-2.5-flash) + rubric fallback,
and logs matches into data/job_hunt.db.
"""

import argparse
import html
import json
import re
import urllib.error
import urllib.request
from typing import Any, Dict, List, Tuple

from gemini_client import call_gemini, extract_json, load_base_resume, load_profile
from tracker import determine_initial_status, get_conn, init_db


def _http_get_json(url: str) -> Any:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 (Antigravity JobHuntAgent/1.0)"},
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode("utf-8"))


def strip_html(raw: str) -> str:
    if not raw:
        return ""
    unescaped = html.unescape(raw)
    clean = re.sub(r"<[^>]+>", " ", unescaped)
    return re.sub(r"\s+", " ", clean).strip()


def fetch_greenhouse_jobs(board_token: str, limit: int = 10) -> List[Dict[str, str]]:
    url = f"https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs?content=true"
    try:
        data = _http_get_json(url)
    except Exception:
        return []
    jobs = []
    for item in data.get("jobs", [])[:limit]:
        jobs.append(
            {
                "company": board_token.capitalize(),
                "title": item.get("title", ""),
                "location": (item.get("location") or {}).get("name", ""),
                "portal": "Greenhouse",
                "url": item.get("absolute_url", ""),
                "description": strip_html(item.get("content", ""))[:4000],
            }
        )
    return jobs


def fetch_lever_jobs(company_slug: str, limit: int = 10) -> List[Dict[str, str]]:
    url = f"https://api.lever.co/v0/postings/{company_slug}?mode=json"
    try:
        data = _http_get_json(url)
    except Exception:
        return []
    jobs = []
    if not isinstance(data, list):
        return []
    for item in data[:limit]:
        categories = item.get("categories") or {}
        jobs.append(
            {
                "company": company_slug.capitalize(),
                "title": item.get("text", ""),
                "location": categories.get("location", ""),
                "portal": "Lever",
                "url": item.get("hostedUrl", ""),
                "description": strip_html(item.get("descriptionPlain", "") or item.get("description", ""))[:4000],
            }
        )
    return jobs


def score_job_with_gemini_or_rubric(
    job: Dict[str, str], profile: Dict[str, Any], resume_text: str
) -> Tuple[int, str]:
    prefs = profile.get("target_preferences", {})
    skills = profile.get("skills", {})
    autonomy = profile.get("autonomy_settings", {})
    model = autonomy.get("scoring_model", "gemini-2.5-flash")

    prompt = f"""
Evaluate how well this job matches the candidate profile on a 0-100 scale.
Return JSON with keys:
- "score": integer 0-100
- "reasoning": 1-2 sentence explanation covering role fit, skill overlap, and location compatibility.

CANDIDATE PROFILE:
{json.dumps(profile, indent=2)}

CANDIDATE RESUME SUMMARY:
{resume_text[:2000]}

JOB POSTING:
Company: {job.get('company')}
Title: {job.get('title')}
Location: {job.get('location')}
Description: {job.get('description', '')[:2500]}
"""
    raw = call_gemini(prompt, model=model, json_output=True)
    parsed = extract_json(raw or "")
    if "score" in parsed:
        try:
            score = max(0, min(100, int(parsed["score"])))
            return score, str(parsed.get("reasoning", "Scored via Gemini."))
        except (ValueError, TypeError):
            pass

    # Deterministic fallback rubric when offline or GEMINI_API_KEY is not yet set
    title_lower = job.get("title", "").lower()
    desc_lower = (job.get("description", "") + " " + title_lower).lower()
    loc_lower = job.get("location", "").lower()

    target_roles = [r.lower() for r in prefs.get("roles", ["software engineer", "backend", "full stack", "ai"])]
    primary_skills = [s.lower() for s in skills.get("primary", ["python", "typescript", "react", "node", "aws"])]
    secondary_skills = [s.lower() for s in skills.get("secondary", [])]
    target_locs = [l.lower() for l in prefs.get("locations", ["remote", "bengaluru", "india"])]

    role_pts = 35 if any(r in title_lower for r in target_roles) else (22 if "engineer" in title_lower or "developer" in title_lower else 8)
    matched_primary = [s for s in primary_skills if s in desc_lower]
    matched_secondary = [s for s in secondary_skills if s in desc_lower]
    skill_pts = min(35, len(matched_primary) * 7 + len(matched_secondary) * 3)
    loc_pts = 15 if any(l in loc_lower for l in target_locs) or "remote" in desc_lower else 8
    stage_pts = 12

    total = max(0, min(100, role_pts + skill_pts + loc_pts + stage_pts))
    reasoning = (
        f"Role fit: {role_pts}/35 | Skills matched ({', '.join(matched_primary[:5]) or 'general'}): "
        f"{skill_pts}/35 | Location fit: {loc_pts}/15"
    )
    return total, reasoning


def save_scored_job(job: Dict[str, str], score: int, reasoning: str, auto_apply_min: int = 80, review_min: int = 60) -> Dict[str, Any]:
    init_db()
    status = determine_initial_status(score, auto_apply_min, review_min)
    import datetime as dt

    now = dt.datetime.now(dt.timezone.utc).isoformat()
    with get_conn() as conn:
        cur = conn.execute(
            """
            INSERT INTO jobs (company, title, location, portal, url, match_score, match_reasoning, description, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(url) DO UPDATE SET
                match_score = excluded.match_score,
                match_reasoning = excluded.match_reasoning,
                description = CASE WHEN excluded.description != '' THEN excluded.description ELSE jobs.description END
            RETURNING id, status;
            """,
            (
                job["company"],
                job["title"],
                job.get("location", ""),
                job.get("portal", "Web"),
                job["url"],
                score,
                reasoning,
                job.get("description", ""),
                status,
                now,
            ),
        )
        row = cur.fetchone()
    return {
        "job_id": row["id"],
        "company": job["company"],
        "title": job["title"],
        "location": job.get("location", ""),
        "portal": job.get("portal", ""),
        "score": score,
        "status": row["status"],
        "reasoning": reasoning,
        "url": job["url"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Scout and score jobs using Gemini + ATS feeds")
    parser.add_argument("--scan-all", action="store_true", help="Scan configured Greenhouse and Lever boards")
    parser.add_argument("--greenhouse", default="", help="Comma-separated Greenhouse board tokens")
    parser.add_argument("--lever", default="", help="Comma-separated Lever company slugs")
    parser.add_argument("--query", default="", help="Optional title keyword filter (e.g. 'Engineer')")
    parser.add_argument("--limit-per-board", type=int, default=8)
    args = parser.parse_args()

    profile = load_profile()
    resume_text = load_base_resume()
    autonomy = profile.get("autonomy_settings", {})
    auto_min = int(autonomy.get("auto_apply_min_score", 80))
    rev_min = int(autonomy.get("review_queue_min_score", 60))

    boards = profile.get("target_boards", {})
    gh_list = [x.strip() for x in args.greenhouse.split(",") if x.strip()]
    lv_list = [x.strip() for x in args.lever.split(",") if x.strip()]

    if args.scan_all:
        gh_list.extend(boards.get("greenhouse_companies", ["stripe", "razorpay", "postman", "vercel"]))
        lv_list.extend(boards.get("lever_companies", ["palantir", "meesho"]))

    discovered: List[Dict[str, str]] = []
    for token in dict.fromkeys(gh_list):
        discovered.extend(fetch_greenhouse_jobs(token, limit=args.limit_per_board))
    for slug in dict.fromkeys(lv_list):
        discovered.extend(fetch_lever_jobs(slug, limit=args.limit_per_board))

    if args.query:
        q = args.query.lower()
        discovered = [j for j in discovered if q in j["title"].lower() or q in j.get("description", "").lower()]

    results = []
    for job in discovered:
        score, reasoning = score_job_with_gemini_or_rubric(job, profile, resume_text)
        saved = save_scored_job(job, score, reasoning, auto_min, rev_min)
        results.append(saved)

    results.sort(key=lambda x: x["score"], reverse=True)
    print(json.dumps({"total_scanned": len(results), "jobs": results}, indent=2))


if __name__ == "__main__":
    main()
