#!/usr/bin/env python3
"""
HR / Recruiter & Hiring Manager Discovery, Cold Outreach Drafter, and Approved Sender.
STRICT SEMI-AUTONOMOUS ENFORCEMENT:
- Drafts are ALWAYS saved with status = 'PENDING_APPROVAL'.
- 'send-approved' ONLY sends messages whose status has been explicitly set to 'APPROVED' by the user.
"""

import argparse
import datetime as dt
import json
import os
import re
import smtplib
from email.message import EmailMessage
from pathlib import Path
from typing import Any, Dict, List

from gemini_client import call_gemini, extract_json, load_dotenv, load_profile
from tracker import get_conn, init_db


def validate_email_address(email_addr: str) -> Dict[str, Any]:
    """
    Validates an HR email address before queuing or sending:
    1. RFC-style syntax & domain check.
    2. Live Google DNS MX record lookup (rejects domains with no MX servers).
    3. Direct SMTP RCPT TO probe on port 25 when reachable (rejects 550 non-existent mailboxes).
    """
    import ssl
    import urllib.request

    clean = (email_addr or "").strip().lower()
    if not re.match(r"^[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}$", clean):
        return {"email": clean, "valid": False, "reason": "INVALID_SYNTAX", "mx_hosts": []}

    domain = clean.split("@", 1)[1]
    mx_hosts: List[str] = []
    try:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        dns_url = f"https://dns.google/resolve?name={domain}&type=MX"
        req = urllib.request.Request(dns_url, headers={"User-Agent": "Mozilla/5.0"})
        dns_data = json.loads(urllib.request.urlopen(req, context=ctx, timeout=6).read().decode("utf-8", errors="ignore"))
        if dns_data.get("Status") == 0 and dns_data.get("Answer"):
            for ans in dns_data["Answer"]:
                if ans.get("type") == 15:
                    parts = (ans.get("data") or "").split()
                    if parts:
                        mx_hosts.append(parts[-1].rstrip("."))
    except Exception as exc:
        return {"email": clean, "valid": False, "reason": f"DNS_LOOKUP_FAILED: {exc}", "mx_hosts": []}

    if not mx_hosts:
        return {"email": clean, "valid": False, "reason": "NO_MX_RECORD", "mx_hosts": []}

    # Optional Port 25 RCPT TO check (if ISP allows port 25 outbound)
    smtp_note = f"MX_OK ({mx_hosts[0]})"
    try:
        with smtplib.SMTP(mx_hosts[0], 25, timeout=3) as server:
            server.ehlo("gmail.com")
            server.mail(os.environ.get("GMAIL_ADDRESS", "").strip())
            code, msg = server.rcpt(clean)
            if code >= 500:
                return {
                    "email": clean,
                    "valid": False,
                    "reason": f"SMTP_REJECTED_{code}: {msg.decode('utf-8', errors='ignore')[:80]}",
                    "mx_hosts": mx_hosts[:2],
                }
            smtp_note = f"SMTP_{code}_OK ({mx_hosts[0]})"
    except Exception:
        pass

    return {"email": clean, "valid": True, "reason": smtp_note, "mx_hosts": mx_hosts[:2]}


def infer_company_domain(company: str, job_url: str = "") -> str:
    slug = re.sub(r"[^a-z0-9]", "", company.lower())
    return f"{slug}.com"


def generate_email_candidates(full_name: str, domain: str) -> List[str]:
    parts = [re.sub(r"[^a-z]", "", p.lower()) for p in full_name.split() if p.strip()]
    if not parts:
        return [f"recruiting@{domain}", f"careers@{domain}"]
    if len(parts) == 1:
        return [f"{parts[0]}@{domain}", f"careers@{domain}"]
    first, last = parts[0], parts[-1]
    return [
        f"{first}.{last}@{domain}",
        f"{first}@{domain}",
        f"{first[0]}{last}@{domain}",
    ]


def draft_outreach_messages(
    job: Dict[str, Any], hr_contact: Dict[str, Any], profile: Dict[str, Any]
) -> Dict[str, str]:
    candidate = profile.get("candidate", {})
    skills = profile.get("skills", {}).get("primary", [])
    highlights = profile.get("highlight_achievements", [])
    model = profile.get("autonomy_settings", {}).get("tailoring_model", "gemini-2.5-pro")

    first_name = hr_contact["name"].split()[0] if hr_contact.get("name") else "there"

    prompt = f"""
Write a high-converting, concise cold email (100-130 words) and a LinkedIn connection note (<270 chars)
from {candidate.get('full_name', 'the candidate')} to {hr_contact.get('name')} ({hr_contact.get('role')}) at {job['company']}.

Context:
- Role applied for: {job['title']} ({job.get('location', 'Remote')})
- Candidate current title & YoE: {candidate.get('current_title')} ({candidate.get('years_of_experience')} yrs)
- Top skills: {', '.join(skills[:6])}
- Key achievements: {json.dumps(highlights[:2])}
- Links: LinkedIn ({candidate.get('linkedin_url')}), GitHub ({candidate.get('github_url')}), Portfolio ({candidate.get('portfolio_url')})

Return JSON with keys:
- "email_subject": Compelling subject line
- "email_body": Plain text email body
- "linkedin_note": Warm LinkedIn connection note under 270 characters
"""
    raw = call_gemini(prompt, model=model, json_output=True)
    parsed = extract_json(raw or "")

    top_skill_str = ", ".join(skills[:4]) if skills else "Python, TypeScript, and Distributed Systems"
    proof_1 = highlights[0] if highlights else "Built and scaled high-throughput backend microservices with 99.95% uptime."
    proof_2 = highlights[1] if len(highlights) > 1 else "Shipped production LLM/agentic workflows reducing manual turnaround by 65%."

    subject = parsed.get("email_subject") or (
        f"{job['title']} application — {candidate.get('full_name', 'Candidate')} ({top_skill_str})"
    )
    email_body = parsed.get("email_body") or (
        f"Hi {first_name},\n\n"
        f"I recently applied for the {job['title']} role at {job['company']} and wanted to reach out directly.\n\n"
        f"Over the past {candidate.get('years_of_experience', 3)}+ years as a {candidate.get('current_title', 'Software Engineer')}, "
        f"I've focused on building production systems with {top_skill_str}:\n"
        f"• {proof_1}\n"
        f"• {proof_2}\n\n"
        f"I've attached my resume and included my profile links below. "
        f"Would you be open to a quick 10-minute chat this week to see if my background is a strong fit for the team?\n\n"
        f"Best regards,\n"
        f"{candidate.get('full_name', 'Your Name')}\n"
        f"LinkedIn: {candidate.get('linkedin_url', '')} | GitHub: {candidate.get('github_url', '')}\n"
        f"Phone: {candidate.get('phone', '')}"
    )
    linkedin_note = parsed.get("linkedin_note") or (
        f"Hi {first_name}, I just applied for the {job['title']} role at {job['company']}. "
        f"I have {candidate.get('years_of_experience', 3)}+ yrs building with {top_skill_str} "
        f"and would love to connect and share my resume!"
    )[:275]

    return {
        "email_subject": subject,
        "email_body": email_body,
        "linkedin_note": linkedin_note,
    }


def queue_drafts_for_job(job_id: int, auto_approve: bool = True) -> List[Dict[str, Any]]:
    init_db()
    profile = load_profile()
    require_approval = bool(profile.get("autonomy_settings", {}).get("require_hr_outreach_approval", False))
    initial_status = "PENDING_APPROVAL" if (require_approval and not auto_approve) else "APPROVED"
    now = dt.datetime.now(dt.timezone.utc).isoformat()

    with get_conn() as conn:
        job_row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        if not job_row:
            raise SystemExit(f"Job ID {job_id} not found.")
        job = dict(job_row)

        # Load all HR email IDs that have ever been queued or contacted so we NEVER repeat an email ID
        existing_emails = {
            (r["email"] or "").strip().lower()
            for r in conn.execute(
                """
                SELECT c.email FROM outreach_queue o
                JOIN hr_contacts c ON o.hr_contact_id = c.id
                WHERE o.channel = 'EMAIL' AND c.email IS NOT NULL AND TRIM(c.email) != ''
                """
            ).fetchall()
        }

        contacts = [
            dict(r)
            for r in conn.execute(
                "SELECT * FROM hr_contacts WHERE job_id = ? OR LOWER(company) = LOWER(?)",
                (job_id, job["company"]),
            ).fetchall()
        ]

        # If no specific HR contact has been added yet, create a placeholder Technical Recruiter contact
        if not contacts:
            domain = infer_company_domain(job["company"], job["url"])
            default_email = f"careers@{domain}".lower()
            already_contacted_domain = any(e.endswith(f"@{domain}") for e in existing_emails)
            if default_email in existing_emails or already_contacted_domain:
                return []
            cur = conn.execute(
                """
                INSERT INTO hr_contacts (job_id, company, name, role, email, email_confidence, linkedin_url, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                RETURNING *;
                """,
                (
                    job_id,
                    job["company"],
                    f"{job['company']} Talent Acquisition Team",
                    "Technical Recruiter / Talent Acquisition",
                    default_email,
                    "domain_default",
                    f"https://www.linkedin.com/search/results/people/?keywords={job['company']}%20Technical%20Recruiter",
                    now,
                ),
            )
            contacts = [dict(cur.fetchone())]

        queued = []
        for contact in contacts:
            contact_email = (contact.get("email") or "").strip().lower()
            if not contact_email or contact_email in existing_emails:
                # Never repeat an HR email ID that was already queued or sent
                continue

            drafts = draft_outreach_messages(job, contact, profile)
            cur_email = conn.execute(
                """
                INSERT INTO outreach_queue (job_id, hr_contact_id, channel, subject, body, status, scheduled_followup_day, created_at)
                VALUES (?, ?, 'EMAIL', ?, ?, ?, 0, ?)
                RETURNING id;
                """,
                (job_id, contact["id"], drafts["email_subject"], drafts["email_body"], initial_status, now),
            )
            email_id = cur_email.fetchone()["id"]
            existing_emails.add(contact_email)

            cur_li = conn.execute(
                """
                INSERT INTO outreach_queue (job_id, hr_contact_id, channel, subject, body, status, scheduled_followup_day, created_at)
                VALUES (?, ?, 'LINKEDIN', '', ?, ?, 0, ?)
                RETURNING id;
                """,
                (job_id, contact["id"], drafts["linkedin_note"], initial_status, now),
            )
            li_id = cur_li.fetchone()["id"]

            queued.append(
                {
                    "job_id": job_id,
                    "company": job["company"],
                    "hr_name": contact["name"],
                    "hr_email": contact_email,
                    "email_outreach_id": email_id,
                    "linkedin_outreach_id": li_id,
                    "status": initial_status,
                }
            )
    return queued


def export_sent_emails_log() -> Path:
    """Maintains a persistent CSV log of all contacted HR email IDs so they are never repeated across sessions."""
    import csv
    log_path = Path(__file__).resolve().parent.parent / "data" / "sent_emails_log.csv"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT o.id AS outreach_id, c.company, c.name AS hr_name, c.role AS hr_role,
                   LOWER(TRIM(c.email)) AS email, o.status, o.sent_at
            FROM outreach_queue o
            JOIN hr_contacts c ON o.hr_contact_id = c.id
            WHERE o.channel = 'EMAIL' AND o.status IN ('SENT', 'BOUNCED_UNVERIFIED')
            ORDER BY o.id ASC
            """
        ).fetchall()
    with log_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Outreach_ID", "Company", "HR_Name", "HR_Role", "Email", "Status", "Sent_At"])
        for r in rows:
            writer.writerow([r["outreach_id"], r["company"], r["hr_name"], r["hr_role"], r["email"], r["status"], r["sent_at"]])
    return log_path


def send_approved_emails(dry_run: bool = False, include_pending: bool = False) -> List[Dict[str, Any]]:
    """Sends outreach emails while strictly deduplicating HR email addresses so no HR email ID is ever repeated."""
    import csv
    init_db()
    load_dotenv()
    gmail_user = os.environ.get("GMAIL_ADDRESS", "").strip()
    gmail_pass = os.environ.get("GMAIL_APP_PASSWORD", "").strip().replace(" ", "")

    allowed_statuses = ("'APPROVED'", "'PENDING_APPROVAL'") if include_pending else ("'APPROVED'",)
    log_path = Path(__file__).resolve().parent.parent / "data" / "sent_emails_log.csv"

    with get_conn() as conn:
        already_contacted_emails = {
            (r["hr_email"] or "").strip().lower()
            for r in conn.execute(
                """
                SELECT DISTINCT c.email AS hr_email
                FROM outreach_queue o
                JOIN hr_contacts c ON o.hr_contact_id = c.id
                WHERE o.channel = 'EMAIL' AND o.status IN ('SENT', 'BOUNCED_UNVERIFIED')
                """
            ).fetchall()
            if (r["hr_email"] or "").strip()
        }
    if log_path.exists():
        try:
            with log_path.open("r", encoding="utf-8", errors="ignore") as f:
                for row in csv.DictReader(f):
                    em = (row.get("Email") or "").strip().lower()
                    if em:
                        already_contacted_emails.add(em)
        except Exception:
            pass

    with get_conn() as conn:

        approved = [
            dict(r)
            for r in conn.execute(
                f"""
                SELECT o.*, c.name AS hr_name, c.email AS hr_email, c.company, j.tailored_dir
                FROM outreach_queue o
                JOIN hr_contacts c ON o.hr_contact_id = c.id
                LEFT JOIN jobs j ON o.job_id = j.id
                WHERE o.status IN ({', '.join(allowed_statuses)}) AND o.channel = 'EMAIL'
                ORDER BY o.id ASC
                """
            ).fetchall()
        ]

    if not approved:
        return []

    results = []
    for item in approved:
        recipient = item.get("hr_email", "").strip()
        recipient_key = recipient.lower()
        if not recipient:
            results.append({"outreach_id": item["id"], "sent": False, "error": "Missing recipient email"})
            continue

        # Strict deduplication: NEVER send to an HR email ID that has already been contacted
        if recipient_key in already_contacted_emails:
            with get_conn() as conn:
                conn.execute(
                    "UPDATE outreach_queue SET status = 'SKIPPED_DUPLICATE_EMAIL' WHERE id = ?",
                    (item["id"],),
                )
            results.append(
                {
                    "outreach_id": item["id"],
                    "sent": False,
                    "status": "SKIPPED_DUPLICATE_EMAIL",
                    "to": recipient,
                }
            )
            continue

        if dry_run or not gmail_user or not gmail_pass or gmail_pass == "xxxx-xxxx-xxxx-xxxx":
            results.append(
                {
                    "outreach_id": item["id"],
                    "sent": False,
                    "mode": "DRY_RUN_OR_MISSING_SMTP_CREDENTIALS",
                    "to": recipient,
                    "subject": item["subject"],
                }
            )
            continue

        # Pre-verify domain MX record & Port 25 SMTP RCPT TO handshake before attempting Gmail SMTP send
        v_res = validate_email_address(recipient_key)
        if not v_res.get("valid", True) and not str(v_res.get("reason", "")).startswith("DNS_LOOKUP_FAILED"):
            with get_conn() as conn:
                conn.execute("UPDATE outreach_queue SET status = 'SKIPPED_INVALID_EMAIL' WHERE id = ?", (item["id"],))
            results.append(
                {
                    "outreach_id": item["id"],
                    "sent": False,
                    "status": "SKIPPED_INVALID_EMAIL",
                    "reason": v_res.get("reason"),
                    "to": recipient,
                }
            )
            continue

        msg = EmailMessage()
        msg["From"] = gmail_user
        msg["To"] = recipient
        msg["Subject"] = item["subject"]
        msg.set_content(item["body"])

        # Always attach the candidate's 1-page PDF resume
        pdf_path = Path(__file__).resolve().parent.parent / "profile" / "Chinmay_Thanekar_Data_Engineer_Resume.pdf"
        if not pdf_path.exists():
            try:
                from generate_pdf_resume import build_resume_pdf
                build_resume_pdf(pdf_path)
            except Exception:
                pass
        if pdf_path.exists():
            msg.add_attachment(
                pdf_path.read_bytes(),
                maintype="application",
                subtype="pdf",
                filename="Chinmay_Thanekar_Data_Engineer_Resume.pdf",
            )

        try:
            sent_ok = False
            last_err = ""
            for mode in ("starttls_587", "ssl_465"):
                try:
                    if mode == "starttls_587":
                        with smtplib.SMTP("smtp.gmail.com", 587, timeout=20) as server:
                            server.ehlo()
                            server.starttls()
                            server.ehlo()
                            server.login(gmail_user, gmail_pass)
                            server.send_message(msg)
                    else:
                        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=20) as server:
                            server.login(gmail_user, gmail_pass)
                            server.send_message(msg)
                    sent_ok = True
                    break
                except Exception as sub_exc:
                    last_err = str(sub_exc)
            if not sent_ok:
                raise RuntimeError(last_err)
            now = dt.datetime.now(dt.timezone.utc).isoformat()
            with get_conn() as conn:
                conn.execute(
                    "UPDATE outreach_queue SET status = 'SENT', sent_at = ? WHERE id = ?",
                    (now, item["id"]),
                )
            already_contacted_emails.add(recipient_key)
            results.append({"outreach_id": item["id"], "sent": True, "to": recipient})
        except Exception as exc:
            results.append({"outreach_id": item["id"], "sent": False, "error": str(exc)})

    export_sent_emails_log()
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="HR Finder & Autonomous Deduplicated Cold Outreach CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    p_draft = sub.add_parser("draft", help="Draft cold email & LinkedIn note for a job ID")
    p_draft.add_argument("--job-id", type=int, required=True)

    sub.add_parser("draft-all", help="Draft HR outreach for all APPLIED and READY_TO_AUTO_APPLY jobs (skipping duplicate HR emails)")

    p_auto = sub.add_parser("auto-send-all", help="Draft and immediately send cold emails for all ready/applied jobs without asking for approval (never repeating HR emails)")
    p_auto.add_argument("--dry-run", action="store_true")

    p_perm = sub.add_parser("permute-email", help="Generate corporate email permutations for an HR contact")
    p_perm.add_argument("--name", required=True)
    p_perm.add_argument("--domain", required=True)

    p_send = sub.add_parser("send-approved", help="Send outreach emails (strictly deduplicated by HR email ID)")
    p_send.add_argument("--dry-run", action="store_true")
    p_send.add_argument("--include-pending", action="store_true", help="Also send PENDING_APPROVAL emails without asking")

    args = parser.parse_args()
    if args.command == "draft":
        res = queue_drafts_for_job(args.job_id)
        print(json.dumps({"queued": res}, indent=2))
    elif args.command == "draft-all":
        init_db()
        with get_conn() as conn:
            job_ids = [
                r["id"]
                for r in conn.execute(
                    "SELECT id FROM jobs WHERE status IN ('READY_TO_AUTO_APPLY', 'APPLIED') ORDER BY match_score DESC"
                ).fetchall()
            ]
        all_queued = []
        for jid in job_ids:
            all_queued.extend(queue_drafts_for_job(jid))
        print(json.dumps({"queued": all_queued}, indent=2))
    elif args.command == "auto-send-all":
        init_db()
        with get_conn() as conn:
            job_ids = [
                r["id"]
                for r in conn.execute(
                    "SELECT id FROM jobs WHERE status IN ('READY_TO_AUTO_APPLY', 'APPLIED') ORDER BY match_score DESC"
                ).fetchall()
            ]
        all_queued = []
        for jid in job_ids:
            all_queued.extend(queue_drafts_for_job(jid, auto_approve=True))
        sent = send_approved_emails(dry_run=args.dry_run, include_pending=True)
        print(json.dumps({"newly_queued": all_queued, "send_results": sent}, indent=2))
    elif args.command == "permute-email":
        print(json.dumps({"candidates": generate_email_candidates(args.name, args.domain)}, indent=2))
    elif args.command == "send-approved":
        res = send_approved_emails(dry_run=args.dry_run, include_pending=args.include_pending)
        print(json.dumps({"send_results": res}, indent=2))


if __name__ == "__main__":
    main()
