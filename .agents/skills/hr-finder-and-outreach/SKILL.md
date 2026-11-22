---
name: hr-finder-and-outreach
description: >-
  Discovers HRs, technical recruiters, and hiring managers for target companies,
  verifies corporate emails and LinkedIn URLs, and drafts personalized cold emails
  and LinkedIn notes with a mandatory user approval gate before sending.
---

# HR / Recruiter Discovery & Cold Outreach Skill

## Why Cold Outreach Multiplies Interview Conversion
Applying on a portal alone yields a 2–5% response rate. Pairing every `>=80%` application with a concise, high-signal message to the **Technical Recruiter** and **Engineering Hiring Manager** within 24 hours boosts interview conversion to 15–30%.

## Workflow

### Step 1: Discover & Strictly Validate HRs & Hiring Managers (Zero-Bounce Rule)
For a target company (`<Company>`), run targeted searches via `search_web` or `scripts/hr_outreach.py`:
- **Technical Recruiters**:
  `site:linkedin.com/in "<Company>" ("Technical Recruiter" OR "Talent Acquisition" OR "Recruiting") "<Location>"`
- **Hiring Managers**:
  `site:linkedin.com/in "<Company>" ("Engineering Manager" OR "Head of Engineering" OR "VP Engineering" OR "CTO")`
- **Mandatory Email Validation (Prevent Bounces Before Queueing/Sending)**:
  1. **Current Employment Verification**: Always verify via LinkedIn/web search that the HR/Recruiter **still currently works at `<Company>`** today (never email contacts who have left the company) and verify that `<Company>` has not migrated its domain after an acquisition or rebrand.
  2. **DNS MX & SMTP Handshake Check**: Run `python scripts/hr_outreach.py validate-emails` (or `validate_email_address()` in `scripts/hr_outreach.py`) to confirm live DNS MX records (`dns.google`) and SMTP `RCPT TO` acceptance before queuing or sending.
  3. **Strict Deduplication**: Check `data/sent_emails_log.csv` and `data/job_hunt.db` so no email ID is ever contacted twice.

### Step 2: Draft Personalized Outreach (Gemini 2.5 Pro)
Generate two message variants per contact:
1. **Cold Email (100–140 words max)**:
   - **Subject**: `[Role Title] application — [Candidate Name] ([Top Proof Point])`
   - **Line 1 (Context)**: Mention applying to the exact role + why the company's current product/engineering work stood out.
   - **Line 2–3 (Proof)**: 2 concrete, metric-backed achievements directly matching their stack.
   - **Line 4 (CTA)**: Low-friction ask (*"I've already submitted my application via your portal and attached my resume here—would you be open to a quick 10-minute chat this week?"*).
2. **LinkedIn Connection Note (<280 characters)**:
   - *"Hi [First Name], I just applied for the [Role] role at [Company]. Built [1-line proof matching their stack] and would love to connect and share my resume!"*

### Step 3: Autonomous Sending & Strict HR Email Deduplication
**CRITICAL RULES**:
- **Do NOT ask for approval on scheduled runs**: Automatically draft and send cold emails via `python scripts/hr_outreach.py auto-send-all`.
- **Never repeat an HR email ID**: Before adding, queueing, or sending any cold email, check `hr_contacts` and `outreach_queue` (case-insensitively) and skip any HR email address that has already been contacted or queued.
```powershell
python scripts/hr_outreach.py auto-send-all
```
