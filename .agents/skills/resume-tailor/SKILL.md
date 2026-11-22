---
name: resume-tailor
description: >-
  ATS resume tailoring, cover letter writing, and application Q&A generation using
  Google Gemini. Use when preparing tailored application materials for a specific job.
---

# ATS Resume & Cover Letter Tailoring Skill

## Tailoring Principles
1. **Truthfulness First**: Never invent employers, dates, degrees, or technologies not supported by [`profile/base_resume.md`](../../../profile/base_resume.md) and [`profile/candidate_profile.yaml`](../../../profile/candidate_profile.yaml).
2. **Exact ATS Keyword Mirroring**: Mirror exact terminology from the job description (e.g., if the JD specifies `FastAPI`, `PostgreSQL`, and `Distributed Systems`, surface those exact phrases in the Summary, Skills section, and top 2 experience bullets).
3. **Quantified Impact**: Prioritize bullets containing metrics (`latency reduced by 45%`, `10k+ RPM`, `65% time saved`).
4. **Screening Question Bank**: Pre-generate answers for common application questions:
   - *"Why do you want to work at [Company]?"*
   - *"Tell us about a challenging system or project you built."*
   - *Work authorization, notice period, and expected compensation.*

## Commands
- Tailor resume & cover letter for a specific job ID:
  ```powershell
  python scripts/tailor_resume.py --job-id <JOB_ID>
  ```
- Tailor all jobs currently in `READY_TO_AUTO_APPLY` (`match_score >= 80`):
  ```powershell
  python scripts/tailor_resume.py --all-ready
  ```

## Output Artifacts
All generated files are stored in `applications/<company_slug>_<job_id>/`:
- `tailored_resume.md`
- `cover_letter.md`
- `screening_answers.json`
- `ats_analysis.json` (matched keywords, missing keywords, tailoring notes)
