#!/usr/bin/env python3
"""
Semi-Autonomous Application Submitter Script.
Enforces the >= 80% match score gate (unless --force is passed by the user),
ensures tailored resume/answers exist, and automates form filling on Greenhouse,
Lever, and Ashby via Playwright with strict timeouts and fast DOM evaluation.
"""

import argparse
import datetime as dt
import json
import re
from pathlib import Path
from typing import Any, Dict

from gemini_client import load_base_resume, load_profile
from tailor_resume import tailor_for_job
from tracker import get_conn, init_db


def prepare_and_check_gate(job_id: int, force: bool = False) -> Dict[str, Any]:
    init_db()
    profile = load_profile()
    min_score = int(profile.get("autonomy_settings", {}).get("auto_apply_min_score", 80))

    with get_conn() as conn:
        row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        if not row:
            raise SystemExit(f"Job ID {job_id} not found.")
        job = dict(row)

    if job["match_score"] < min_score and not force:
        with get_conn() as conn:
            conn.execute("UPDATE jobs SET status = 'REVIEW_REQUIRED' WHERE id = ?", (job_id,))
        return {
            "job_id": job_id,
            "allowed": False,
            "status": "REVIEW_REQUIRED",
            "reason": (
                f"Match score ({job['match_score']}%) is below the semi-autonomous threshold ({min_score}%). "
                "Requires explicit user confirmation (--force) to apply."
            ),
        }

    tailored_dir = Path(job["tailored_dir"]) if job.get("tailored_dir") else None
    if not tailored_dir or not tailored_dir.exists():
        tailored_dir = tailor_for_job(job, profile, load_base_resume())

    answers_path = tailored_dir / "screening_answers.json"
    screening_answers = json.loads(answers_path.read_text(encoding="utf-8")) if answers_path.exists() else {}

    return {
        "job_id": job_id,
        "allowed": True,
        "company": job["company"],
        "title": job["title"],
        "url": job["url"],
        "portal": job["portal"],
        "match_score": job["match_score"],
        "tailored_dir": str(tailored_dir),
        "resume_path": str(tailored_dir / "tailored_resume.md"),
        "cover_letter_path": str(tailored_dir / "cover_letter.md"),
        "candidate": profile.get("candidate", {}),
        "preferences": profile.get("target_preferences", {}),
        "screening_answers": screening_answers,
    }


def _dropdown_choice_for_label(label_text: str) -> list[str]:
    l = label_text.lower()
    if "school" in l or "university" in l or "institution" in l:
        return ["Pune", "Savitribai", "Other", "Not Listed", "India"]
    if "discipline" in l or "major" in l or "field of study" in l:
        return ["Computer Science", "Computer Engineering", "Information Technology", "Engineering", "Other"]
    if "degree" in l and "do you have" not in l:
        return ["Bachelor's Degree", "Bachelor of Engineering", "Bachelor", "B.E.", "B.Tech"]
    if "start date month" in l:
        return ["July", "Jul"]
    if "end date month" in l:
        return ["November", "Nov", "Present"]
    if "debezium" in l or "peerdb" in l:
        return ["Basic Knowledge", "Hands on Experience", "No exposure"]
    if "how many years" in l or "overall experience" in l or "years of experience" in l or "experiece" in l or "experience in number" in l:
        return ["3-5yrs", "3-5", "4 to 5", "3 to 5", "Less than 5 Years", "4-6", "3 - 5", "4+", "3+", "4", "5", "Yes"]
    if "already on notice" in l or "other offer in hand" in l or "offer in hand" in l:
        return ["No"]
    if "notice period" in l or "how soon can you join" in l:
        return ["90", "60-90", "3 months", "60", "30", "Immediate"]
    if (
        "sponsorship" in l
        or "sponsor you" in l
        or "visa" in l
        or "immigration" in l
        or "previously employed" in l
        or "previously worked" in l
        or "previously applied" in l
        or "ever been employed" in l
        or "former employee" in l
        or "employed by" in l
        or "government official" in l
        or "relatives" in l
        or "close relative" in l
        or "family members" in l
        or "outside business" in l
        or "conflict of interest" in l
        or "referred to this position" in l
        or "non-compete" in l
    ):
        return ["No", "None", "Not Applicable"]
    if "gender" in l or "sex" in l or "diversity" in l:
        return ["Male", "Man", "Prefer not to", "Decline"]
    if "hispanic" in l or "latino" in l:
        return ["No", "Decline", "Prefer not to"]
    if "race" in l or "ethnicity" in l:
        return ["Asian", "South Asian", "Prefer not to", "Decline"]
    if "veteran" in l or "disability" in l or "handicap" in l or "lgbt" in l or "sexual orientation" in l:
        return ["I am not", "No", "I do not", "Prefer not to", "Decline"]
    if "pronoun" in l:
        return ["He/Him", "He / Him", "he/him", "Prefer not to", "Decline"]
    if "recorded" in l or "consent" in l or "privacy" in l or "acknowledge" in l or "terms" in l or "gdpr" in l or "confirm receipt" in l:
        return ["Confirmed", "I consent", "Yes", "I Agree", "Agree", "Accept"]
    if "ai tools today" in l:
        return ["regularly", "every week", "use AI tools"]
    if (
        "4+ years" in l
        or "comfortable working" in l
        or "at least 18" in l
        or "background check" in l
        or "authorized" in l
        or "legally eligible" in l
        or "right to work" in l
        or "willing" in l
        or "based out of" in l
        or "relocate" in l
        or "hybrid" in l
        or "onsite" in l
        or "office" in l
        or "india national" in l
        or "6 months" in l
        or "bachelor" in l
        or "aptitude test" in l
        or "whatsapp" in l
    ):
        return ["Yes", "I Agree", "Agree"]
    if "how did you hear" in l or "how did you get to know" in l or "source" in l:
        return ["LinkedIn", "Linkedin", "Job Board", "Company Website", "Careers Page", "Other"]
    if "locations do you live" in l or "country" in l or "located" in l or "location" in l:
        return ["India", "Pune", "Bengaluru", "Bangalore", "Hyderabad", "Mumbai", "Other"]
    return ["Yes", "India", "No"]


def _text_value_for_label(
    ltext: str,
    cand: Dict[str, Any],
    prefs: Dict[str, Any],
    first_name: str,
    last_name: str,
    full_name: str,
    raw_phone: str,
    today_str: str,
) -> str:
    l = ltext.lower()
    if "first name" in l and "preferred" not in l:
        return first_name
    if "last name" in l:
        return last_name
    if "preferred first name" in l or "preferred name" in l:
        return first_name
    if "full name" in l or l == "name" or l == "name*":
        return full_name
    if "email" in l:
        return cand.get("email", "")
    if "phone" in l or "mobile" in l or "contact number" in l:
        return raw_phone
    if "start date year" in l:
        return "2022"
    if "end date year" in l:
        return "2026"
    if "current company" in l or "current employer" in l or "previous employer" in l or "current firm" in l or "organization" in l or "company name" in l:
        return "Cognizant Technology Solutions India Pvt Ltd"
    if "current title" in l or "job title" in l or "designation" in l or "current role" in l or l.startswith("title"):
        return "Data Engineer"
    if "offered ctc" in l:
        return "N/A"
    if "last working day" in l:
        return (dt.date.today() + dt.timedelta(days=30)).isoformat()
    if "current" in l and ("ctc" in l or "salary" in l or "compensation" in l):
        return str(cand.get("current_ctc_lpa", ""))
    if ("expected" in l or "desired" in l) and ("ctc" in l or "salary" in l or "compensation" in l):
        return str(prefs.get("min_compensation_inr_lpa", cand.get("expected_ctc_lpa", "")))
    if "notice period" in l or "how soon" in l or "start date" in l or "available to start" in l:
        return "90 days (negotiable)"
    if "relatives at" in l or "relatives currently" in l:
        return "No"
    if "willing to work in" in l:
        return "Yes"
    if "reason for job change" in l:
        return "Seeking a challenging Data Engineering role building large-scale cloud data platforms."
    if "pyspark" in l or "spark" in l:
        return "4+ years building production batch and event-driven ETL pipelines in PySpark and Apache Spark on AWS EMR and Databricks."
    if "iceberg" in l or "delta lake" in l or "hudi" in l:
        return "Yes — 4+ years processing large-scale enterprise datasets and maintaining consistency across 27 applications using Apache Spark on Databricks and Delta Lake."
    if "aws" in l or "cloud" in l:
        return "AWS S3, AWS Glue (Jobs, Data Catalog, Crawlers), AWS EMR, Amazon Redshift, Redshift Spectrum, Athena, Lambda, Step Functions, IAM, CloudWatch, CloudFormation."
    if "dbt" in l or "airflow" in l:
        return "4 years orchestrating production ETL workflows in Apache Airflow with retry logic, dependency management, and alerting."
    if "linkedin" in l:
        return cand.get("linkedin_url", "")
    if "website" in l or "github" in l or "portfolio" in l or "blog" in l:
        return cand.get("github_url", "")
    if "if yes, please" in l or "n/a" in l or "name of the employee" in l or "referred by" in l or "referral" in l:
        return "N/A"
    if "mailing address" in l or "address" in l or "city" in l or "current location" in l or "where are you based" in l or "location" in l:
        return "Pune, Maharashtra, India"
    if "working status" in l or "citizen" in l or "authorization" in l or "visa" in l:
        return "Indian Citizen (Authorized to work in India without sponsorship)"
    if "type your name and the date" in l or "certification" in l or "signature" in l:
        return f"{full_name} - {today_str}"
    if "how many years" in l or "years of experience" in l or "total experience" in l or "relevant experience" in l or "total years" in l:
        return "4"
    if "university" in l or "college" in l or "school" in l or "education" in l:
        return "Savitribai Phule Pune University (B.E.)"
    if "degree" in l:
        return "Bachelor of Engineering (B.E.)"
    if "why" in l or "excites you" in l or "interest" in l or "cover letter" in l or "additional information" in l:
        return (
            "I am a Data Engineer with 4+ years of production experience at Cognizant building scalable cloud-native ETL/ELT "
            "and Lakehouse pipelines using Apache Spark, PySpark, Python, SQL, AWS (S3, Glue, EMR, Redshift, Step Functions, Lambda, Athena), "
            "Databricks, Delta Lake, and Apache Airflow."
        )
    return ""


def attempt_playwright_submission(bundle: Dict[str, Any], dry_run: bool = False, headed: bool = False) -> Dict[str, Any]:
    try:
        from playwright.sync_api import sync_playwright  # type: ignore
    except ImportError:
        return {
            "submitted_via_playwright": False,
            "ready_for_browser_subagent": True,
            "note": "Playwright not installed; prepared pre-filled payload for Antigravity browser agent / Chrome DevTools.",
            "payload": bundle,
        }

    cand = bundle["candidate"]
    prefs = bundle.get("preferences", {})
    full_name = cand.get("full_name", "")
    parts = full_name.split(" ", 1)
    first_name = parts[0]
    last_name = parts[1] if len(parts) > 1 else ""
    raw_phone = cand.get("phone", "").replace("+91-", "").replace("+91", "").strip()
    pdf_resume = Path(__file__).resolve().parent.parent / "profile" / "Chinmay_Thanekar_Data_Engineer_Resume.pdf"

    screenshot_path = Path(bundle["tailored_dir"]) / "application_form_prefilled.png"
    submitted_sub_path = Path(bundle["tailored_dir"]) / "application_submitted.png"
    filled_fields = []
    submitted_live = False
    remaining_errors = 0

    target_url = bundle["url"]
    if "jobs.lever.co/" in target_url and not target_url.rstrip("/").endswith("/apply"):
        target_url = target_url.rstrip("/") + "/apply"
    if "jobs.ashbyhq.com/" in target_url and not target_url.rstrip("/").endswith("/application"):
        target_url = target_url.rstrip("/") + "/application"

    with sync_playwright() as p:
        browser = None
        for ch in ("chrome", "msedge", None):
            try:
                browser = (
                    p.chromium.launch(channel=ch, headless=not headed, timeout=10000)
                    if ch
                    else p.chromium.launch(headless=not headed, timeout=10000)
                )
                break
            except Exception:
                continue
        if browser is None:
            return {
                "submitted_via_playwright": False,
                "error": "Could not launch Chrome, Edge, or Chromium via Playwright.",
            }

        page = browser.new_page()
        page.set_default_timeout(2500)
        try:
            page.goto(target_url, wait_until="domcontentloaded", timeout=20000)
            page.wait_for_timeout(2000)

            # If a Greenhouse URL redirected to a custom corporate domain, open the direct Greenhouse embed URL!
            m_gh = re.search(r"greenhouse\.io/([^/]+)/jobs/(\d+)", target_url)
            if m_gh and "greenhouse.io" not in page.url:
                board_tok, gh_jid = m_gh.group(1), m_gh.group(2)
                embed_url = f"https://job-boards.greenhouse.io/embed/job_app?for={board_tok}&token={gh_jid}"
                page.goto(embed_url, wait_until="domcontentloaded", timeout=20000)
                page.wait_for_timeout(2000)

            # 1. Upload PDF Resume to first file input (and Cover Letter if a second file input remains in DOM)
            if pdf_resume.exists():
                file_inputs = page.locator("input[type='file']")
                if file_inputs.count() > 0:
                    try:
                        file_inputs.first.set_input_files(str(pdf_resume), timeout=3000)
                        filled_fields.append("Resume PDF uploaded")
                        if "lever.co" in page.url:
                            page.wait_for_timeout(5500)
                        else:
                            page.wait_for_timeout(1500)
                    except Exception:
                        pass
                # After Resume upload on Greenhouse, the first input[type='file'] is replaced by the filename pill,
                # so any remaining input[type='file'] is the Cover Letter / Work Sample upload!
                if "lever.co" not in page.url and page.locator("input[type='file']").count() > 0:
                    try:
                        page.locator("input[type='file']").first.set_input_files(str(pdf_resume), timeout=3000)
                        filled_fields.append("Cover Letter PDF uploaded")
                        page.wait_for_timeout(1200)
                    except Exception:
                        pass

            today_str = dt.date.today().isoformat()

            # 2A. LEVER SPECIFIC FORM FILLING (if on jobs.lever.co)
            if "lever.co" in page.url:
                cookie_btn = page.locator("button:has-text('ACCEPT'), button:has-text('Accept'), button:has-text('Dismiss')").first
                if cookie_btn.count() > 0 and cookie_btn.is_visible():
                    try:
                        cookie_btn.click(timeout=800)
                    except Exception:
                        pass

                lever_map = [
                    ("input[name='name']", full_name, "Full Name"),
                    ("input[name='email']", cand.get("email", ""), "Email"),
                    ("input[name='phone']", f"+91{raw_phone}", "Phone"),
                    ("input[name='org']", "Cognizant Technology Solutions India Pvt Ltd", "Current Company"),
                    ("input[name='location'], input[id='location-input']", "Pune, Maharashtra, India", "Current Location"),
                    ("input[name='urls[LinkedIn]'], input[name*='LinkedIn' i]", cand.get("linkedin_url", ""), "LinkedIn"),
                    ("input[name='urls[GitHub]'], input[name*='GitHub' i]", cand.get("github_url", ""), "GitHub"),
                    ("input[name='urls[Portfolio]']", cand.get("github_url", ""), "Portfolio"),
                    (
                        "textarea[name='comments']",
                        "Data Engineer with 4+ years of experience at Cognizant building scalable batch and real-time data pipelines using Apache Spark, PySpark, Python, SQL, AWS (S3, Glue, EMR, Redshift, Athena, Step Functions, Lambda), Databricks, Delta Lake, and Apache Airflow.",
                        "Comments",
                    ),
                ]
                for sel, val, label_name in lever_map:
                    loc = page.locator(sel).first
                    if loc.count() > 0:
                        try:
                            loc.fill(val, timeout=1000)
                            filled_fields.append(f"Lever[{label_name}]")
                        except Exception:
                            pass

                page.wait_for_timeout(600)
                loc_dropdown = page.locator(".lever-dropdown-result, .autocomplete-suggestion, .dropdown-results div").first
                if loc_dropdown.count() > 0 and loc_dropdown.is_visible():
                    try:
                        loc_dropdown.click(timeout=800)
                    except Exception:
                        pass

                questions = page.locator("li.application-question, div.application-question")
                q_count = questions.count()
                for idx in range(q_count):
                    q = questions.nth(idx)
                    try:
                        q_text = (q.inner_text(timeout=500) or "").strip()
                    except Exception:
                        q_text = ""
                    if not q_text:
                        continue
                    ql = q_text.lower()
                    if any(
                        k in ql
                        for k in (
                            "resume/cv",
                            "full name",
                            "current company",
                            "linkedin url",
                            "twitter url",
                            "github url",
                            "portfolio url",
                            "other website",
                            "stackoverflow url",
                            "naukri url",
                            "other url",
                            "additional information",
                        )
                    ):
                        continue

                    radios = q.locator("input[type='radio']")
                    if radios.count() > 0:
                        choices = _dropdown_choice_for_label(q_text)
                        picked_r = False
                        for c in choices:
                            r_lbl = q.locator(f"label:has-text('{c}')").first
                            if r_lbl.count() > 0:
                                try:
                                    r_lbl.click(timeout=800)
                                    picked_r = True
                                    filled_fields.append(f"LeverRadio[{q_text[:22]}]={c}")
                                    break
                                except Exception:
                                    pass
                        if not picked_r:
                            try:
                                radios.first.check(force=True, timeout=800)
                                filled_fields.append(f"LeverRadio[{q_text[:22]}]=first")
                            except Exception:
                                pass
                        continue

                    sel_el = q.locator("select").first
                    if sel_el.count() > 0:
                        choices = _dropdown_choice_for_label(q_text)
                        try:
                            opts = sel_el.locator("option").all_inner_texts()
                            picked_opt = None
                            for c in choices:
                                for o in opts:
                                    if c.lower() in o.lower() and "select" not in o.lower() and "choose" not in o.lower():
                                        picked_opt = o
                                        break
                                if picked_opt:
                                    break
                            if not picked_opt and len(opts) > 1:
                                picked_opt = opts[1]
                            if picked_opt:
                                sel_el.select_option(label=picked_opt, timeout=800)
                                filled_fields.append(f"LeverSelect[{q_text[:22]}]={picked_opt}")
                        except Exception:
                            pass
                        continue

                    txt_el = q.locator("input[type='text'], input[type='number'], textarea").first
                    if txt_el.count() > 0:
                        inp_name = (txt_el.get_attribute("name") or "").lower()
                        if inp_name in ("name", "email", "phone", "org", "location", "comments") or inp_name.startswith("urls["):
                            continue
                        val = _text_value_for_label(q_text, cand, prefs, first_name, last_name, full_name, raw_phone, today_str)
                        if not val:
                            val = "Yes — 4+ years of production Data Engineering experience with Apache Spark, PySpark, Python, SQL, AWS, Databricks, and Airflow."
                        try:
                            txt_el.fill(val, timeout=800)
                            filled_fields.append(f"LeverInput[{q_text[:22]}]")
                        except Exception:
                            pass

                loc_in = page.locator("input[name='location'], input[id='location-input']").first
                if loc_in.count() > 0:
                    try:
                        loc_in.fill("Pune, Maharashtra, India", timeout=800)
                    except Exception:
                        pass

                checkboxes = page.locator("input[type='checkbox'][name*='consent'], input[type='checkbox'][required], input[type='checkbox']")
                for c_idx in range(checkboxes.count()):
                    try:
                        checkboxes.nth(c_idx).check(force=True, timeout=800)
                        filled_fields.append("LeverCheckbox[Consent]")
                    except Exception:
                        pass

            # 2B. GREENHOUSE / STANDARD LABEL[FOR] FORM FILLING
            label_Target_pairs = page.evaluate(
                """() => {
                    const out = [];
                    document.querySelectorAll('label').forEach(lbl => {
                        const forId = lbl.getAttribute('for');
                        const text = (lbl.innerText || '').trim();
                        if (!forId || !text) return;
                        const el = document.getElementById(forId);
                        if (!el) return;
                        const tag = el.tagName.toLowerCase();
                        const role = (el.getAttribute('role') || '').toLowerCase();
                        const type = (el.getAttribute('type') || 'text').toLowerCase();
                        out.push({forId, text, tag, role, type});
                    });
                    return out;
                }"""
            )

            for item in label_Target_pairs:
                for_id = item["forId"]
                ltext = item["text"]
                l = ltext.lower()
                tag = item["tag"]
                role = item["role"]
                itype = item["type"]

                loc = page.locator(f"[id='{for_id}']").first
                if tag == "select":
                    choices = _dropdown_choice_for_label(ltext)
                    try:
                        opts = loc.locator("option").all_inner_texts()
                        picked_opt = None
                        for c in choices:
                            for o in opts:
                                if c.lower() in o.lower() and "select" not in o.lower() and "choose" not in o.lower():
                                    picked_opt = o
                                    break
                            if picked_opt:
                                break
                        if not picked_opt and len(opts) > 1:
                            picked_opt = opts[1]
                        if picked_opt:
                            loc.select_option(label=picked_opt, timeout=800)
                            filled_fields.append(f"Select[{ltext[:24]}]={picked_opt}")
                    except Exception:
                        pass
                elif role == "combobox":
                    if len(l) < 15 and "country" in l:
                        try:
                            loc.scroll_into_view_if_needed(timeout=1000)
                            loc.click(timeout=1000, force=True)
                            page.keyboard.type("India", delay=40)
                            page.wait_for_timeout(350)
                            opt_in = page.locator("[role='option']:visible:has-text('+91')").first
                            if opt_in.count() > 0:
                                opt_in.click(timeout=1000, force=True)
                            else:
                                page.keyboard.press("Enter")
                            filled_fields.append("Dropdown[Country*]=+91")
                        except Exception:
                            pass
                        continue
                    if "location (city)" in l or l.startswith("city"):
                        try:
                            loc.scroll_into_view_if_needed(timeout=1000)
                            loc.click(timeout=1000, force=True)
                            page.keyboard.type("Pune, Maharashtra, India", delay=50)
                            page.wait_for_timeout(1200)
                            opt_city = page.locator("[role='option']:visible").first
                            if opt_city.count() > 0:
                                opt_city.click(timeout=1000, force=True)
                            else:
                                page.keyboard.press("ArrowDown")
                                page.wait_for_timeout(200)
                                page.keyboard.press("Enter")
                            filled_fields.append("Dropdown[Location (City)*]=Pune, India")
                        except Exception:
                            pass
                        continue
                    choices = _dropdown_choice_for_label(ltext)
                    try:
                        loc.scroll_into_view_if_needed(timeout=1000)
                        loc.click(timeout=1200, force=True)
                        page.wait_for_timeout(350)
                        picked = False
                        for c in choices:
                            opt = page.locator(f"[role='option']:visible:has-text('{c}')").first
                            if opt.count() > 0:
                                opt.click(timeout=1000, force=True)
                                picked = True
                                filled_fields.append(f"Dropdown[{ltext[:24]}]={c}")
                                break
                        if not picked:
                            first_opt = page.locator("[role='option']:visible").first
                            if first_opt.count() > 0:
                                first_opt.click(timeout=1000, force=True)
                                picked = True
                                filled_fields.append(f"Dropdown[{ltext[:24]}]=first_option")
                        if not picked:
                            page.keyboard.press("ArrowDown")
                            page.wait_for_timeout(150)
                            page.keyboard.press("Enter")
                            filled_fields.append(f"Dropdown[{ltext[:24]}]=ArrowDown_Enter")
                        page.wait_for_timeout(200)
                    except Exception:
                        pass
                elif tag in ("input", "textarea") and itype not in ("file", "checkbox", "radio", "hidden", "submit"):
                    val = _text_value_for_label(ltext, cand, prefs, first_name, last_name, full_name, raw_phone, today_str)
                    if not val and "*" in ltext:
                        val = "Yes — 4+ years of production Data Engineering experience at Cognizant."
                    if val:
                        try:
                            loc.fill(val, timeout=1000)
                            filled_fields.append(f"Field[{ltext[:24]}]")
                        except Exception:
                            pass

            # Handle Greenhouse required checkbox groups intelligently per fieldset (never check all boxes blindly!)
            if "lever.co" not in page.url:
                fieldsets = page.locator("fieldset")
                for fs_idx in range(fieldsets.count()):
                    fs = fieldsets.nth(fs_idx)
                    if fs.locator("input[type='checkbox']").count() == 0:
                        continue
                    try:
                        fs_text = (fs.inner_text(timeout=500) or "").lower()
                    except Exception:
                        fs_text = ""
                    target_labels = []
                    if "prior question" in fs_text:
                        target_labels = ["Not applicable", "None of these"]
                    elif "cuba" in fs_text or "sanctions" in fs_text:
                        target_labels = ["None of the above"]
                    elif "country or countries you anticipate" in fs_text:
                        target_labels = ["India"]
                    elif "backend languages" in fs_text:
                        target_labels = ["Python"]
                    elif "personally implemented in production" in fs_text:
                        target_labels = ["Data sharding or partitioning", "Retry / idempotency mechanisms"]
                    else:
                        target_labels = ["Yes", "I acknowledge", "I agree", "Confirm"]

                    checked_in_fs = False
                    for t_lbl in target_labels:
                        cb_lbl = fs.locator(f"label:has-text('{t_lbl}')").first
                        if cb_lbl.count() > 0:
                            try:
                                cb_lbl.click(timeout=800)
                                checked_in_fs = True
                                filled_fields.append(f"Checkbox[{t_lbl[:20]}]")
                                if "personally implemented" not in fs_text:
                                    break
                            except Exception:
                                pass
                    if not checked_in_fs and "*" in fs_text:
                        try:
                            fs.locator("input[type='checkbox']").first.check(force=True, timeout=800)
                            filled_fields.append("Checkbox[FirstInFieldset]")
                        except Exception:
                            pass

                # Ensure Education Degree & Discipline (#degree--0, #discipline--0) and dynamically revealed #race are explicitly selected if present
                for edu_id, edu_query in (("#degree--0", "Bachelor"), ("#discipline--0", "Computer"), ("#race", "Asian")):
                    edu_loc = page.locator(edu_id).first
                    if edu_loc.count() > 0:
                        try:
                            edu_loc.scroll_into_view_if_needed(timeout=1000)
                            edu_loc.click(timeout=1000, force=True)
                            page.keyboard.type(edu_query, delay=40)
                            page.wait_for_timeout(450)
                            opt_edu = page.locator(f"[role='option']:visible:has-text('{edu_query}')").first
                            if opt_edu.count() > 0:
                                opt_edu.click(timeout=1000, force=True)
                            else:
                                page.keyboard.press("ArrowDown")
                                page.wait_for_timeout(150)
                                page.keyboard.press("Enter")
                            filled_fields.append(f"Edu[{edu_id}]={edu_query}")
                            page.wait_for_timeout(250)
                        except Exception:
                            pass

                # Check any standalone consent checkbox ("By checking this box, I consent...") outside multi-option fieldsets
                consent_lbls = page.locator("label:has-text('By checking this box'), label:has-text('I consent to')")
                for cl_idx in range(consent_lbls.count()):
                    try:
                        consent_lbls.nth(cl_idx).click(timeout=800)
                        filled_fields.append("Checkbox[Consent]")
                    except Exception:
                        pass

            # Ensure Country (+91) is set right before final screenshot & submit on Greenhouse
            country_loc = page.locator("#country").first
            if country_loc.count() > 0 and "lever.co" not in page.url:
                try:
                    country_loc.scroll_into_view_if_needed(timeout=1000)
                    country_loc.click(timeout=1000, force=True)
                    page.keyboard.type("India", delay=40)
                    page.wait_for_timeout(350)
                    opt_in = page.locator("[role='option']:visible:has-text('+91')").first
                    if opt_in.count() > 0:
                        opt_in.click(timeout=1000, force=True)
                    else:
                        page.keyboard.press("Enter")
                except Exception:
                    pass

            page.screenshot(path=str(screenshot_path), full_page=True)

            # 3. Click submit and handle Greenhouse Email OTP verification automatically if prompted
            if not dry_run and len(filled_fields) >= 2:
                if "lever.co" in page.url:
                    submit_btn = page.locator("#btn-submit, button.postings-btn, button:has-text('Submit application')").first
                else:
                    submit_btn = page.locator(
                        "button[type='submit']:visible, input[type='submit']:visible, button:has-text('Submit application'), button:has-text('Submit Application')"
                    ).first

                if submit_btn.count() > 0:
                    try:
                        submit_btn.click(force=True, timeout=3000)
                        page.wait_for_timeout(5000)
                        page.screenshot(path=str(submitted_sub_path), full_page=True)
                        body_text = (page.locator("body").inner_text(timeout=2000) or "").lower()

                        # Check if Greenhouse asked for the 8-character security code sent to Gmail
                        if "security code" in body_text or "verification code" in body_text:
                            from gemini_client import load_dotenv
                            import email as py_email
                            import imaplib
                            import os
                            import time

                            load_dotenv()
                            g_user = os.environ.get("GMAIL_ADDRESS", "").strip()
                            g_pass = os.environ.get("GMAIL_APP_PASSWORD", "").strip().replace(" ", "")
                            otp_code = ""
                            if g_user and g_pass:
                                for _ in range(5):
                                    time.sleep(3)
                                    try:
                                        with imaplib.IMAP4_SSL("imap.gmail.com") as mail:
                                            mail.login(g_user, g_pass)
                                            mail.select("inbox")
                                            _, data = mail.search(None, '(UNSEEN FROM "greenhouse")')
                                            ids = data[0].split()
                                            if not ids:
                                                _, data = mail.search(None, '(FROM "greenhouse")')
                                                ids = data[0].split()
                                            if ids:
                                                _, msg_data = mail.fetch(ids[-1], "(RFC822)")
                                                raw_email = msg_data[0][1].decode("utf-8", errors="ignore")
                                                msg_obj = py_email.message_from_string(raw_email)
                                                payload_txt = ""
                                                if msg_obj.is_multipart():
                                                    for part in msg_obj.walk():
                                                        if part.get_content_type() in ("text/plain", "text/html"):
                                                            payload_txt += part.get_payload(decode=True).decode("utf-8", errors="ignore")
                                                else:
                                                    payload_txt = msg_obj.get_payload(decode=True).decode("utf-8", errors="ignore")
                                                clean_txt = re.sub(r"<style[^>]*>.*?</style>", " ", payload_txt, flags=re.S | re.I)
                                                clean_txt = re.sub(r"<[^>]+>", " ", clean_txt)
                                                m_after = re.search(
                                                    r"application:\s*([A-Za-z0-9]{8})\b",
                                                    clean_txt,
                                                    re.I,
                                                )
                                                if m_after:
                                                    otp_code = m_after.group(1)
                                                else:
                                                    for tok in re.findall(r"\b([A-Za-z0-9]{8})\b", clean_txt):
                                                        if any(c.isdigit() for c in tok) and any(c.isalpha() for c in tok):
                                                            otp_code = tok
                                                            break
                                                if otp_code:
                                                    break
                                    except Exception:
                                        pass
                            if otp_code:
                                code_input = page.locator("input[id*='security'], input[name*='security'], input[aria-label*='code' i]").first
                                if code_input.count() > 0:
                                    code_input.click(timeout=1000)
                                    code_input.press_sequentially(otp_code, delay=40)
                                    filled_fields.append(f"Greenhouse_OTP={otp_code}")
                                    page.wait_for_timeout(500)
                                    submit_btn.click(force=True, timeout=3000)
                                    page.wait_for_timeout(4500)
                                    page.screenshot(path=str(submitted_sub_path), full_page=True)

                        check_state = page.evaluate(
                            """() => {
                                const body = (document.body.innerText || '').toLowerCase();
                                const url = window.location.href.toLowerCase();
                                const errs = Array.from(document.querySelectorAll('*')).filter(
                                    el => el.children.length === 0 && ((el.innerText || '').includes('This field is required') || (el.innerText || '').includes('Select a country') || (el.innerText || '').includes('Phone number is too long'))
                                ).length;
                                const thankYou = (
                                    body.includes('thank you for applying') ||
                                    body.includes('application has been submitted') ||
                                    body.includes('application submitted') ||
                                    body.includes('thanks for applying') ||
                                    url.includes('thanks') ||
                                    url.includes('confirmation')
                                );
                                return {
                                    thankYou: thankYou,
                                    errs: errs
                                };
                            }"""
                        )
                        remaining_errors = int(check_state.get("errs", 0))
                        if check_state.get("thankYou"):
                            submitted_live = True
                    except Exception:
                        pass
        except Exception as exc:
            browser.close()
            return {
                "submitted_via_playwright": False,
                "filled_fields": filled_fields,
                "error": str(exc),
            }
        browser.close()

    now = dt.datetime.now(dt.timezone.utc).isoformat()
    if submitted_live:
        new_status = "APPLIED"
    elif remaining_errors > 0:
        new_status = "NEEDS_USER_INPUT"
    elif filled_fields:
        new_status = "PREFILLED_SCREENSHOT_SAVED"
    else:
        new_status = "PORTAL_VISITED"

    with get_conn() as conn:
        conn.execute(
            "UPDATE jobs SET status = ?, applied_at = CASE WHEN ? = 'APPLIED' THEN ? ELSE applied_at END WHERE id = ?",
            (new_status, new_status, now, bundle["job_id"]),
        )

    return {
        "submitted_via_playwright": submitted_live,
        "new_status": new_status,
        "remaining_required_errors": remaining_errors,
        "filled_fields": filled_fields,
        "prefilled_screenshot": str(screenshot_path) if screenshot_path.exists() else "",
        "post_submit_screenshot": str(submitted_sub_path) if submitted_sub_path.exists() else "",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Semi-autonomous job application runner (>=80% match gate)")
    parser.add_argument("--job-id", type=int, default=None)
    parser.add_argument("--all-ready", action="store_true", help="Process all jobs with match_score >= 80")
    parser.add_argument("--force", action="store_true", help="Override >=80% gate with explicit user approval")
    parser.add_argument("--dry-run", action="store_true", help="Prepare and prefill without final submit")
    parser.add_argument("--headed", action="store_true", help="Run browser in visible window")
    args = parser.parse_args()

    init_db()
    if args.job_id is not None:
        job_ids = [args.job_id]
    elif args.all_ready:
        with get_conn() as conn:
            job_ids = [
                r["id"]
                for r in conn.execute(
                    "SELECT id FROM jobs WHERE status = 'READY_TO_AUTO_APPLY' AND match_score >= 80 ORDER BY match_score DESC"
                ).fetchall()
            ]
    else:
        raise SystemExit("Provide --job-id <ID> or --all-ready")

    results = []
    for jid in job_ids:
        bundle = prepare_and_check_gate(jid, force=args.force)
        if not bundle.get("allowed"):
            results.append(bundle)
            continue
        sub_res = attempt_playwright_submission(bundle, dry_run=args.dry_run, headed=args.headed)
        results.append({**bundle, "submission": sub_res})

    print(json.dumps({"processed": len(results), "results": results}, indent=2))


if __name__ == "__main__":
    main()
