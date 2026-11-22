#!/usr/bin/env python3
"""
Generates / updates data/outreach_launcher.html directly from data/job_hunt.db.
Provides 1-click pre-filled Gmail Compose and LinkedIn connection buttons
for all queued, approved, and sent outreach items.
"""

import html
import sqlite3
import urllib.parse
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
DB_PATH = ROOT_DIR / "data" / "job_hunt.db"
OUT_HTML = ROOT_DIR / "data" / "outreach_launcher.html"


def generate_launcher() -> Path:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    rows = conn.execute(
        """
        SELECT 
            o.id AS outreach_id,
            o.channel,
            o.subject,
            o.body,
            o.status AS outreach_status,
            c.name AS hr_name,
            c.role AS hr_role,
            c.email AS hr_email,
            c.linkedin_url AS hr_linkedin,
            j.id AS job_id,
            j.company,
            j.title AS job_title,
            j.match_score,
            j.url AS job_url,
            j.status AS job_status
        FROM outreach_queue o
        JOIN hr_contacts c ON o.hr_contact_id = c.id
        LEFT JOIN jobs j ON o.job_id = j.id
        ORDER BY o.id ASC
        """
    ).fetchall()

    cards = []
    for r in rows:
        ch = r["channel"]
        out_id = r["outreach_id"]
        status = r["outreach_status"]
        company = r["company"] or "Target Company"
        job_title = r["job_title"] or "Data Engineer"
        score = r["match_score"] or 90
        hr_name = r["hr_name"] or "Talent Acquisition Team"
        hr_role = r["hr_role"] or "Technical Recruiter"
        hr_email = r["hr_email"] or ""
        job_url = r["job_url"] or ""
        hr_linkedin = r["hr_linkedin"] or f"https://www.linkedin.com/search/results/people/?keywords={urllib.parse.quote(company + ' Recruiter')}"
        subject = r["subject"] or ""
        body = r["body"] or ""

        status_badge = f'<span class="badge-status {status.lower()}">{status}</span>'

        if ch == "EMAIL":
            su_encoded = urllib.parse.quote(subject)
            body_encoded = urllib.parse.quote(body)
            gmail_link = f"https://mail.google.com/mail/?view=cm&fs=1&to={urllib.parse.quote(hr_email)}&su={su_encoded}&body={body_encoded}"
            mailto_link = f"mailto:{urllib.parse.quote(hr_email)}?subject={su_encoded}&body={body_encoded}"

            card = f"""
        <div class="card">
          <div class="header">
            <span class="badge">Outreach #{out_id} • EMAIL ({score}% Match)</span>
            {status_badge}
            <strong>{html.escape(company)} — {html.escape(job_title)}</strong>
          </div>
          <p class="meta"><strong>To:</strong> {html.escape(hr_name)} ({html.escape(hr_role)}) &lt;{html.escape(hr_email)}&gt;</p>
          <p class="meta"><strong>Subject:</strong> {html.escape(subject)}</p>
          <pre>{html.escape(body)}</pre>
          <div class="actions">
            <a class="btn primary" href="{gmail_link}" target="_blank">Send in Gmail Web (1-Click Pre-filled)</a>
            <a class="btn" href="{mailto_link}">Open in Mail App</a>
            {f'<a class="btn" href="{html.escape(job_url)}" target="_blank">Open Job Application Page</a>' if job_url else ''}
          </div>
        </div>"""
            cards.append(card)
        else:
            card = f"""
        <div class="card">
          <div class="header">
            <span class="badge li">Outreach #{out_id} • LINKEDIN</span>
            {status_badge}
            <strong>{html.escape(company)} — {html.escape(hr_name)}</strong>
          </div>
          <pre>{html.escape(body)}</pre>
          <div class="actions">
            <a class="btn li-btn" href="{html.escape(hr_linkedin)}" target="_blank">Open LinkedIn Profile / Search for {html.escape(hr_name)}</a>
            {f'<a class="btn" href="{html.escape(job_url)}" target="_blank">Open Job Application Page</a>' if job_url else ''}
          </div>
        </div>"""
            cards.append(card)

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Chinmay Thanekar — HR Outreach & Application Launcher</title>
<style>
  body {{ font-family: system-ui, -apple-system, sans-serif; background: #0f172a; color: #f8fafc; max-width: 1000px; margin: 0 auto; padding: 24px; }}
  h1 {{ color: #38bdf8; }}
  .card {{ background: #1e293b; border: 1px solid #334155; border-radius: 10px; padding: 18px; margin-bottom: 16px; }}
  .header {{ display: flex; gap: 12px; align-items: center; margin-bottom: 8px; flex-wrap: wrap; }}
  .badge {{ background: #0284c7; color: white; padding: 3px 10px; border-radius: 999px; font-size: 12px; font-weight: 600; }}
  .badge.li {{ background: #0a66c2; }}
  .badge-status {{ padding: 2px 8px; border-radius: 6px; font-size: 11px; font-weight: 700; text-transform: uppercase; }}
  .badge-status.approved {{ background: #065f46; color: #34d399; }}
  .badge-status.sent {{ background: #1e3a8a; color: #93c5fd; }}
  .badge-status.pending_approval {{ background: #854d0e; color: #fde047; }}
  .badge-status.skipped {{ background: #475569; color: #cbd5e1; }}
  .badge-status.bounced_unverified {{ background: #7f1d1d; color: #fca5a5; }}
  .meta {{ margin: 4px 0; color: #cbd5e1; font-size: 14px; }}
  pre {{ background: #0f172a; padding: 12px; border-radius: 6px; white-space: pre-wrap; color: #e2e8f0; font-size: 13px; border: 1px solid #334155; }}
  .actions {{ display: flex; gap: 10px; margin-top: 12px; flex-wrap: wrap; }}
  .btn {{ text-decoration: none; padding: 8px 14px; border-radius: 6px; font-size: 13px; font-weight: 600; background: #334155; color: #f8fafc; }}
  .btn.primary {{ background: #10b981; color: #052e16; }}
  .btn.li-btn {{ background: #38bdf8; color: #082f49; }}
</style>
</head>
<body>
  <h1>Chinmay Thanekar — All-India Data Engineer Outreach & Apply Launcher</h1>
  <p>Total Tracked Outreach Messages: <strong>{len(rows)}</strong>. Click <strong>"Send in Gmail Web (1-Click Pre-filled)"</strong> to open Gmail Compose with the recipient, subject, and body pre-populated, or use your 16-character Google App Password in <code>.env</code> for automated SMTP.</p>
  {''.join(cards)}
</body>
</html>
"""
    OUT_HTML.write_text(html_content, encoding="utf-8")
    return OUT_HTML


if __name__ == "__main__":
    out = generate_launcher()
    print(f"Generated launcher with {out.stat().st_size} bytes at {out}")
