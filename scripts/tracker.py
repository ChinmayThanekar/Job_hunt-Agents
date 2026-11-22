#!/usr/bin/env python3
"""
SQLite State Tracker for the Antigravity Job Hunt Agent Swarm.
Tracks discovered jobs, match scores, tailored resume paths, application statuses,
HR/Recruiter contacts, and the mandatory approval queue for HR outreach.
"""

import argparse
import csv
import datetime as dt
import json
import sqlite3
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
DB_PATH = ROOT_DIR / "data" / "job_hunt.db"


def get_conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with get_conn() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                company TEXT NOT NULL,
                title TEXT NOT NULL,
                location TEXT DEFAULT '',
                portal TEXT DEFAULT '',
                url TEXT UNIQUE NOT NULL,
                match_score INTEGER DEFAULT 0,
                match_reasoning TEXT DEFAULT '',
                description TEXT DEFAULT '',
                status TEXT DEFAULT 'DISCOVERED',
                tailored_dir TEXT DEFAULT '',
                applied_at TEXT DEFAULT '',
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS hr_contacts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id INTEGER,
                company TEXT NOT NULL,
                name TEXT NOT NULL,
                role TEXT DEFAULT 'Technical Recruiter',
                email TEXT DEFAULT '',
                email_confidence TEXT DEFAULT 'pattern',
                linkedin_url TEXT DEFAULT '',
                created_at TEXT NOT NULL,
                FOREIGN KEY (job_id) REFERENCES jobs(id)
            );

            CREATE TABLE IF NOT EXISTS outreach_queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id INTEGER,
                hr_contact_id INTEGER NOT NULL,
                channel TEXT NOT NULL, -- 'EMAIL' or 'LINKEDIN'
                subject TEXT DEFAULT '',
                body TEXT NOT NULL,
                status TEXT DEFAULT 'PENDING_APPROVAL', -- PENDING_APPROVAL, APPROVED, SENT, SKIPPED
                scheduled_followup_day INTEGER DEFAULT 0,
                sent_at TEXT DEFAULT '',
                created_at TEXT NOT NULL,
                FOREIGN KEY (job_id) REFERENCES jobs(id),
                FOREIGN KEY (hr_contact_id) REFERENCES hr_contacts(id)
            );
            """
        )


def determine_initial_status(score: int, auto_apply_threshold: int = 80, review_threshold: int = 60) -> str:
    if score >= auto_apply_threshold:
        return "READY_TO_AUTO_APPLY"
    if score >= review_threshold:
        return "REVIEW_REQUIRED"
    return "LOW_MATCH"


def cmd_add_job(args: argparse.Namespace) -> None:
    init_db()
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    status = args.status or determine_initial_status(args.score)
    with get_conn() as conn:
        cur = conn.execute(
            """
            INSERT INTO jobs (company, title, location, portal, url, match_score, match_reasoning, description, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(url) DO UPDATE SET
                match_score = excluded.match_score,
                match_reasoning = CASE WHEN excluded.match_reasoning != '' THEN excluded.match_reasoning ELSE jobs.match_reasoning END,
                description = CASE WHEN excluded.description != '' THEN excluded.description ELSE jobs.description END
            RETURNING id, status;
            """,
            (
                args.company,
                args.title,
                args.location or "",
                args.portal or "Web",
                args.url,
                args.score,
                args.reasoning or "",
                args.description or "",
                status,
                now,
            ),
        )
        row = cur.fetchone()
        print(json.dumps({"job_id": row["id"], "status": row["status"], "match_score": args.score}))


def cmd_list_jobs(args: argparse.Namespace) -> None:
    init_db()
    query = "SELECT id, company, title, location, portal, match_score, status, url, tailored_dir, applied_at FROM jobs WHERE 1=1"
    params = []
    if args.status:
        query += " AND status = ?"
        params.append(args.status)
    if args.min_score is not None:
        query += " AND match_score >= ?"
        params.append(args.min_score)
    query += " ORDER BY match_score DESC, id DESC LIMIT ?"
    params.append(args.limit)

    with get_conn() as conn:
        rows = [dict(r) for r in conn.execute(query, params).fetchall()]
    if args.json:
        print(json.dumps(rows, indent=2))
        return

    if not rows:
        print("No jobs found matching criteria.")
        return

    print(f"{'ID':<4} | {'Score':<5} | {'Status':<20} | {'Company':<18} | {'Title':<32} | {'Location':<18} | {'Portal'}")
    print("-" * 120)
    for r in rows:
        print(
            f"{r['id']:<4} | {str(r['match_score']) + '%':<5} | {r['status']:<20} | "
            f"{r['company'][:18]:<18} | {r['title'][:32]:<32} | {r['location'][:18]:<18} | {r['portal']}"
        )


def cmd_get_job(args: argparse.Namespace) -> None:
    init_db()
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM jobs WHERE id = ?", (args.id,)).fetchone()
    if not row:
        raise SystemExit(f"Job ID {args.id} not found.")
    print(json.dumps(dict(row), indent=2))


def cmd_update_job(args: argparse.Namespace) -> None:
    init_db()
    updates = []
    params = []
    if args.status:
        updates.append("status = ?")
        params.append(args.status)
        if args.status == "APPLIED":
            updates.append("applied_at = ?")
            params.append(dt.datetime.now(dt.timezone.utc).isoformat())
    if args.tailored_dir:
        updates.append("tailored_dir = ?")
        params.append(args.tailored_dir)
    if args.score is not None:
        updates.append("match_score = ?")
        params.append(args.score)
    if not updates:
        raise SystemExit("No fields specified to update.")
    params.append(args.id)
    with get_conn() as conn:
        conn.execute(f"UPDATE jobs SET {', '.join(updates)} WHERE id = ?", params)
    print(json.dumps({"updated_job_id": args.id, "status": args.status}))


def cmd_add_hr_contact(args: argparse.Namespace) -> None:
    init_db()
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    clean_email = (args.email or "").strip()
    with get_conn() as conn:
        if clean_email:
            existing = conn.execute(
                "SELECT id, name, company, email FROM hr_contacts WHERE LOWER(TRIM(email)) = LOWER(?)",
                (clean_email,),
            ).fetchone()
            if existing:
                print(
                    json.dumps(
                        {
                            "hr_contact_id": existing["id"],
                            "name": existing["name"],
                            "company": existing["company"],
                            "email": existing["email"],
                            "deduplicated": True,
                        }
                    )
                )
                return
        cur = conn.execute(
            """
            INSERT INTO hr_contacts (job_id, company, name, role, email, email_confidence, linkedin_url, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            RETURNING id;
            """,
            (
                args.job_id,
                args.company,
                args.name,
                args.role or "Technical Recruiter",
                clean_email,
                args.confidence or "pattern",
                args.linkedin_url or "",
                now,
            ),
        )
        row = cur.fetchone()
    print(json.dumps({"hr_contact_id": row["id"], "name": args.name, "company": args.company, "email": clean_email}))


def cmd_queue_outreach(args: argparse.Namespace) -> None:
    init_db()
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    channel = args.channel.upper()
    with get_conn() as conn:
        contact = conn.execute("SELECT email FROM hr_contacts WHERE id = ?", (args.hr_contact_id,)).fetchone()
        contact_email = (contact["email"] if contact else "").strip()
        if channel == "EMAIL" and contact_email:
            dup = conn.execute(
                """
                SELECT o.id, o.status FROM outreach_queue o
                JOIN hr_contacts c ON o.hr_contact_id = c.id
                WHERE o.channel = 'EMAIL' AND LOWER(TRIM(c.email)) = LOWER(?)
                """,
                (contact_email,),
            ).fetchone()
            if dup:
                print(
                    json.dumps(
                        {
                            "outreach_id": dup["id"],
                            "status": "SKIPPED_DUPLICATE_EMAIL",
                            "email": contact_email,
                            "note": "HR email ID already exists in outreach_queue; duplicate skipped.",
                        }
                    )
                )
                return
        cur = conn.execute(
            """
            INSERT INTO outreach_queue (job_id, hr_contact_id, channel, subject, body, status, scheduled_followup_day, created_at)
            VALUES (?, ?, ?, ?, ?, 'APPROVED', ?, ?)
            RETURNING id;
            """,
            (
                args.job_id,
                args.hr_contact_id,
                channel,
                args.subject or "",
                args.body,
                args.followup_day or 0,
                now,
            ),
        )
        row = cur.fetchone()
    print(
        json.dumps(
            {
                "outreach_id": row["id"],
                "status": "APPROVED",
                "note": "Queued as APPROVED (deduplicated HR email).",
            }
        )
    )


def cmd_list_pending_outreach(args: argparse.Namespace) -> None:
    init_db()
    status_filter = args.status or "PENDING_APPROVAL"
    with get_conn() as conn:
        rows = [
            dict(r)
            for r in conn.execute(
                """
                SELECT
                    o.id AS outreach_id,
                    o.status,
                    o.channel,
                    o.subject,
                    o.body,
                    o.scheduled_followup_day,
                    c.name AS hr_name,
                    c.role AS hr_role,
                    c.company,
                    c.email,
                    c.linkedin_url,
                    j.title AS job_title
                FROM outreach_queue o
                JOIN hr_contacts c ON o.hr_contact_id = c.id
                LEFT JOIN jobs j ON o.job_id = j.id
                WHERE o.status = ?
                ORDER BY o.id ASC
                """,
                (status_filter,),
            ).fetchall()
        ]
    if args.json:
        print(json.dumps(rows, indent=2))
        return
    if not rows:
        print(f"No outreach messages with status '{status_filter}'.")
        return
    for r in rows:
        print("=" * 88)
        print(
            f"[Outreach #{r['outreach_id']}] Status: {r['status']} | Channel: {r['channel']} "
            f"| Company: {r['company']} ({r['job_title'] or 'General'})"
        )
        print(f"To: {r['hr_name']} ({r['hr_role']}) | Email: {r['email'] or 'N/A'} | LinkedIn: {r['linkedin_url'] or 'N/A'}")
        if r["subject"]:
            print(f"Subject: {r['subject']}")
        print("-" * 88)
        print(r["body"])
        print()


def cmd_approve_outreach(args: argparse.Namespace) -> None:
    init_db()
    ids = [int(x.strip()) for x in args.ids.split(",") if x.strip()]
    if not ids:
        raise SystemExit("Provide comma-separated outreach IDs via --ids")
    new_status = "SKIPPED" if args.skip else "APPROVED"
    placeholders = ",".join("?" for _ in ids)
    with get_conn() as conn:
        conn.execute(
            f"UPDATE outreach_queue SET status = ? WHERE id IN ({placeholders})",
            [new_status, *ids],
        )
    print(json.dumps({"updated_outreach_ids": ids, "new_status": new_status}))


def cmd_stats(_: argparse.Namespace) -> None:
    init_db()
    with get_conn() as conn:
        job_counts = dict(
            conn.execute("SELECT status, COUNT(*) FROM jobs GROUP BY status").fetchall()
        )
        outreach_counts = dict(
            conn.execute("SELECT status, COUNT(*) FROM outreach_queue GROUP BY status").fetchall()
        )
        total_contacts = conn.execute("SELECT COUNT(*) FROM hr_contacts").fetchone()[0]
    summary = {
        "jobs_by_status": job_counts,
        "hr_contacts_discovered": total_contacts,
        "outreach_by_status": outreach_counts,
    }
    print(json.dumps(summary, indent=2))


def cmd_export_csv(args: argparse.Namespace) -> None:
    init_db()
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with get_conn() as conn:
        rows = [dict(r) for r in conn.execute("SELECT * FROM jobs ORDER BY match_score DESC").fetchall()]
    if not rows:
        print("No jobs to export.")
        return
    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    print(f"Exported {len(rows)} jobs to {out_path}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Job Hunt Swarm SQLite Tracker CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init", help="Initialize SQLite database tables")

    p_add = sub.add_parser("add-job", help="Add or update a discovered job")
    p_add.add_argument("--company", required=True)
    p_add.add_argument("--title", required=True)
    p_add.add_argument("--location", default="")
    p_add.add_argument("--portal", default="Web")
    p_add.add_argument("--url", required=True)
    p_add.add_argument("--score", type=int, default=0)
    p_add.add_argument("--reasoning", default="")
    p_add.add_argument("--description", default="")
    p_add.add_argument("--status", default="")

    p_list = sub.add_parser("list-jobs", help="List tracked jobs")
    p_list.add_argument("--status", default="")
    p_list.add_argument("--min-score", type=int, default=None)
    p_list.add_argument("--limit", type=int, default=50)
    p_list.add_argument("--json", action="store_true")

    p_get = sub.add_parser("get-job", help="Get details of a single job")
    p_get.add_argument("--id", type=int, required=True)

    p_upd = sub.add_parser("update-job", help="Update job status or tailored resume directory")
    p_upd.add_argument("--id", type=int, required=True)
    p_upd.add_argument("--status", default="")
    p_upd.add_argument("--tailored-dir", default="")
    p_upd.add_argument("--score", type=int, default=None)

    p_hr = sub.add_parser("add-hr-contact", help="Add an HR/Recruiter or Hiring Manager contact")
    p_hr.add_argument("--job-id", type=int, default=None)
    p_hr.add_argument("--company", required=True)
    p_hr.add_argument("--name", required=True)
    p_hr.add_argument("--role", default="Technical Recruiter")
    p_hr.add_argument("--email", default="")
    p_hr.add_argument("--confidence", default="pattern")
    p_hr.add_argument("--linkedin-url", default="")

    p_q = sub.add_parser("queue-outreach", help="Queue an HR outreach message for mandatory user approval")
    p_q.add_argument("--job-id", type=int, default=None)
    p_q.add_argument("--hr-contact-id", type=int, required=True)
    p_q.add_argument("--channel", choices=["EMAIL", "LINKEDIN", "email", "linkedin"], default="EMAIL")
    p_q.add_argument("--subject", default="")
    p_q.add_argument("--body", required=True)
    p_q.add_argument("--followup-day", type=int, default=0)

    p_lp = sub.add_parser("list-pending-outreach", help="List outreach messages waiting for user approval")
    p_lp.add_argument("--status", default="PENDING_APPROVAL")
    p_lp.add_argument("--json", action="store_true")

    p_app = sub.add_parser("approve-outreach", help="Approve or skip outreach messages by ID")
    p_app.add_argument("--ids", required=True, help="Comma-separated outreach IDs, e.g., 1,2,3")
    p_app.add_argument("--skip", action="store_true", help="Mark as SKIPPED instead of APPROVED")

    sub.add_parser("stats", help="Show pipeline statistics")

    p_exp = sub.add_parser("export-csv", help="Export jobs table to CSV")
    p_exp.add_argument("--output", default=str(ROOT_DIR / "data" / "jobs_export.csv"))

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    if args.command == "init":
        init_db()
        print(json.dumps({"status": "initialized", "db_path": str(DB_PATH)}))
    elif args.command == "add-job":
        cmd_add_job(args)
    elif args.command == "list-jobs":
        cmd_list_jobs(args)
    elif args.command == "get-job":
        cmd_get_job(args)
    elif args.command == "update-job":
        cmd_update_job(args)
    elif args.command == "add-hr-contact":
        cmd_add_hr_contact(args)
    elif args.command == "queue-outreach":
        cmd_queue_outreach(args)
    elif args.command == "list-pending-outreach":
        cmd_list_pending_outreach(args)
    elif args.command == "approve-outreach":
        cmd_approve_outreach(args)
    elif args.command == "stats":
        cmd_stats(args)
    elif args.command == "export-csv":
        cmd_export_csv(args)


if __name__ == "__main__":
    main()
