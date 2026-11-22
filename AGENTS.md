# Job Hunt Multi-Agent Swarm (`AGENTS.md`)

This workspace powers a **Semi-Autonomous Multi-Agent Job Hunting System** built natively for Antigravity using specialized subagents, workspace skills, and Google Gemini (`gemini-2.5-flash` / `gemini-2.5-pro`).

## Architecture & Agent Roster

When the user asks to hunt for jobs, apply to roles, find HRs, or prepare for interviews, coordinate the following 5 specialized subagents (via `invoke_subagent` or the corresponding skills in `.agents/skills/`):

1. **`job-scout`** (*Job Discovery & Match Scoring Agent*)
   - Searches across **Greenhouse, Lever, Ashby, Workday, LinkedIn, Wellfound, YC Work at a Startup, Indeed, and Naukri**.
   - Evaluates each job against [`profile/candidate_profile.yaml`](./profile/candidate_profile.yaml) and [`profile/base_resume.md`](./profile/base_resume.md) using Gemini (`0–100%` match score).
   - Saves jobs into the local SQLite database (`data/job_hunt.db`) via [`scripts/tracker.py`](./scripts/tracker.py).

2. **`resume-tailor`** (*ATS Resume & Application Tailor Agent*)
   - Extracts ATS keywords and requirements for matched roles.
   - Generates tailored resumes (`tailored_resume.md`), concise cover letters (`cover_letter.md`), and screening question answers (`screening_answers.json`) in `applications/<company>_<job_id>/` without fabricating experience.

3. **`auto-applier`** (*Semi-Autonomous Application Submitter Agent*)
   - Automatically fills and submits applications for jobs with **`match_score >= 80`** using browser tools / [`scripts/auto_apply.py`](./scripts/auto_apply.py).
   - Queues jobs with `60 <= match_score < 80` (or applications blocked by CAPTCHAs/OTPs) as `REVIEW_REQUIRED` for user confirmation.

4. **`hr-outreach`** (*HR, Recruiter & Hiring Manager Outreach Agent*)
   - Finds Technical Recruiters, Talent Acquisition leads, and Hiring Managers at the target company.
   - Discovers and **strictly validates** corporate email addresses and LinkedIn profile URLs before queuing or sending so emails do not bounce back.
   - Drafts and sends high-converting cold emails, LinkedIn connection notes (<280 chars), and Day 3 / Day 7 follow-ups.
   - **AUTO-SEND ON SCHEDULE & STRICT EMAIL DEDUPLICATION**: Scheduled runs (10:00 AM and 2:00 PM) automatically send cold emails without asking for user approval (`python scripts/hr_outreach.py auto-send-all`), and **NEVER** repeat or send more than once to any HR email ID (`hr_contacts.email`) already in `data/job_hunt.db` or `data/sent_emails_log.csv`.

5. **`interview-coach`** (*Inbox Monitor & Interview Prep Agent*)
   - Tracks HR replies and follow-up schedules.
   - Builds role-specific interview dossiers (`interview_prep.md`) with company research, system design/technical questions, and tailored STAR stories as soon as an interview is landed.

---

## Strict Autonomy & Safety Rules

- **Auto-Apply Threshold (`>= 80%`)**:
  - `match_score >= 80`: Auto-tailor resume and auto-apply (`READY_TO_AUTO_APPLY` -> `APPLIED`).
  - `match_score < 80`: Do **not** auto-apply unless explicitly instructed by the user. Mark as `REVIEW_REQUIRED`.
- **Autonomous HR Outreach, Strict Email Deduplication & Mandatory Anti-Bounce Validation**:
  - Do **not** ask for approval during scheduled runs — automatically draft and send cold emails via `python scripts/hr_outreach.py auto-send-all`.
  - **Never repeat an HR email ID**: Before adding, queueing, or sending any cold email, check `hr_contacts`, `outreach_queue`, and `data/sent_emails_log.csv` (case-insensitively) and skip any HR email address that has already been contacted or queued.
  - **Mandatory Email Validation (Zero-Bounce Rule)**: While finding or selecting any HR email ID (from LinkedIn, web search, or CSV lists), ALWAYS validate the email before queuing or sending:
    1. **Current Company Tenure Check**: Verify via LinkedIn/web search that the recruiter/HR contact **still currently works at that company** (skip anyone who has moved to another employer) and that the company's current email domain has not changed due to a rebrand or acquisition.
    2. **DNS MX & SMTP Verification (`validate_email_address`)**: Verify via Google DNS (`https://dns.google/resolve?name=<domain>&type=MX`) that the domain has live MX servers and perform an SMTP `RCPT TO` check where supported; never send to domains without valid MX records or mailboxes returning `550`.
    3. **Never Guess Blind Email Patterns**: Prefer published recruiter emails, verified active contacts, or official recruiting inboxes (`careers@`, `ta@`, `hr@`) verified to accept mail.
- **No Resume Fabrication**:
  - Never invent employers, job titles, degrees, or metrics not grounded in [`profile/base_resume.md`](./profile/base_resume.md) or [`profile/candidate_profile.yaml`](./profile/candidate_profile.yaml).
