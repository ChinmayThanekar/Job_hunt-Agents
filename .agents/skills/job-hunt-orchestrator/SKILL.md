---
name: job-hunt-orchestrator
description: >-
  End-to-end multi-agent job hunt orchestrator. Use this skill when the user wants
  to run a full job hunting cycle: scouting jobs across portals, scoring matches with
  Gemini, tailoring resumes, auto-applying to >=80% match jobs, finding HRs/recruiters,
  and queuing personalized outreach messages for user approval.
---

# Job Hunt Swarm Orchestrator Skill

Coordinates the 5 specialized subagents (`job-scout`, `resume-tailor`, `auto-applier`, `hr-outreach`, and `interview-coach`) and the local SQLite state tracker (`data/job_hunt.db`).

## End-to-End Execution Pipeline

### Step 1: Initialize & Verify Candidate Profile
1. Ensure the SQLite tracker is initialized:
   ```powershell
   python scripts/tracker.py init
   ```
2. Check [`profile/candidate_profile.yaml`](../../../profile/candidate_profile.yaml) and [`profile/base_resume.md`](../../../profile/base_resume.md). If the user hasn't filled in their real name/resume yet, offer to parse their existing PDF/DOCX/text resume into `profile/base_resume.md` and `profile/candidate_profile.yaml`.

### Step 2: Parallel Job Discovery & Gemini Match Scoring (`job-scout`)
1. Invoke the `job-scout` subagent (or run [`scripts/job_scout.py`](../../../scripts/job_scout.py)):
   ```powershell
   python scripts/job_scout.py --query "Software Engineer" --limit 25
   ```
2. Every discovered role is scored `0–100%` against `candidate_profile.yaml`:
   - **`match_score >= 80`**: Tagged `READY_TO_AUTO_APPLY`
   - **`60 <= match_score < 80`**: Tagged `REVIEW_REQUIRED`
   - **`match_score < 60`**: Tagged `SKIPPED`

### Step 3: ATS Resume & Application Tailoring (`resume-tailor`)
1. For every job marked `READY_TO_AUTO_APPLY` (or explicitly selected by the user), invoke `resume-tailor` or run:
   ```powershell
   python scripts/tailor_resume.py --all-ready
   ```
2. Generates `applications/<company>_<job_id>/tailored_resume.md`, `cover_letter.md`, and `screening_answers.json`.

### Step 4: Semi-Autonomous Application Submission (`auto-applier`)
1. Invoke `auto-applier` for jobs with `match_score >= 80`:
   ```powershell
   python scripts/auto_apply.py --all-ready
   ```
2. For portal forms requiring browser interaction (Greenhouse, Lever, Ashby, Workday, LinkedIn Easy Apply, Wellfound), `auto-applier` fills fields, uploads the tailored resume, and updates job status to `APPLIED`.

### Step 5: HR & Hiring Manager Discovery + Autonomous Cold Email Sending (`hr-outreach`)
1. For every `APPLIED` (or high-priority `>= 80%`) job, run `hr-outreach` to discover new recruiters/hiring managers, strictly deduplicate HR email IDs (never repeating any HR email address already in `data/job_hunt.db`), and immediately send cold emails without asking for approval:
   ```powershell
   python scripts/hr_outreach.py auto-send-all
   ```
