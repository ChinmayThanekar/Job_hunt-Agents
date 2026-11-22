---
name: auto-apply
description: >-
  Semi-autonomous job application submission skill. Automatically fills and submits
  applications for jobs with >=80% match score across Greenhouse, Lever, Ashby,
  LinkedIn Easy Apply, Workday, and Wellfound.
---

# Semi-Autonomous Job Application Skill

## Autonomy Gate (Mandatory Check)
Before submitting any job application:
1. Verify `match_score >= 80` in `data/job_hunt.db` (or confirm explicit user approval for `<80%` jobs).
2. Verify `applications/<company_slug>_<job_id>/tailored_resume.md` and `screening_answers.json` exist.

## Portal Playbooks

### 1. Greenhouse (`boards.greenhouse.io` / `job-boards.greenhouse.io`)
- Fill `#first_name`, `#last_name`, `#email`, `#phone`.
- Upload tailored resume file to `input[type="file"]` for Resume/CV.
- Fill LinkedIn URL, GitHub/Portfolio URL, and custom text questions from `screening_answers.json`.

### 2. Lever (`jobs.lever.co/.../apply`)
- Upload tailored resume first (Lever auto-parses fields, so re-verify and overwrite `name`, `email`, `phone`, `org`, `urls[LinkedIn]`, `urls[GitHub]`, `urls[Portfolio]`).
- Fill `comments` with the tailored cover letter / pitch.

### 3. Ashby (`jobs.ashbyhq.com/.../application`)
- Fill standard system fields (`_systemfield_name`, `_systemfield_email`, `_systemfield_resume`) and custom application questions.

### 4. LinkedIn Easy Apply / Wellfound / Workday
- Use browser plugin (Browserbase / Chrome DevTools) or `python scripts/auto_apply.py --job-id <ID> --headed` so the user's authenticated browser session is used.
- If a CAPTCHA or email verification code (OTP) appears, pause and mark status as `NEEDS_USER_INPUT`.

## Commands
- Run auto-apply for a specific job:
  ```powershell
  python scripts/auto_apply.py --job-id <JOB_ID>
  ```
- Dry-run / prefill verification (fills form and saves screenshot without clicking final submit):
  ```powershell
  python scripts/auto_apply.py --job-id <JOB_ID> --dry-run
  ```
