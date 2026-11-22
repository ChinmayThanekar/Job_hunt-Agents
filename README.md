# Job Hunt Multi-Agent System

A semi-autonomous, multi-agent job hunting system built for [Antigravity](https://antigravity.google) and Google Gemini.
It scouts jobs across ATS boards, scores them against your profile, tailors resumes and cover letters, auto-applies to strong matches, and runs validated HR outreach.

See [`AGENTS.md`](./AGENTS.md) for the agent roster and safety rules, and [`.agents/skills/`](./.agents/skills/) for each skill.

## Layout

| Path | Purpose |
| --- | --- |
| `scripts/job_scout.py` | Job discovery (Greenhouse, Lever, Ashby, …) + Gemini match scoring |
| `scripts/tailor_resume.py` | ATS resume / cover letter / screening answer generation |
| `scripts/auto_apply.py` | Playwright-based application submission (≥ 80% match) |
| `scripts/hr_outreach.py` | HR discovery, MX/SMTP email validation, deduplicated cold emails |
| `scripts/tracker.py` | SQLite tracker (`data/job_hunt.db`) |
| `scripts/gemini_client.py` | Gemini REST client + profile loader |
| `scripts/generate_pdf_resume.py` | Dependency-free 1-page PDF resume generator |
| `scripts/generate_launcher.py` | HTML launcher for queued outreach |

## Setup

```powershell
# 1. Secrets
Copy-Item .env.example .env            # then add your Gemini key / Gmail app password

# 2. Your profile (kept local, gitignored)
Copy-Item profile/candidate_profile.example.yaml profile/candidate_profile.yaml
Copy-Item profile/base_resume.example.md profile/base_resume.md

# 3. Optional dependencies
pip install pyyaml playwright
playwright install chromium
```

## Privacy

The following are **gitignored** and never committed: `.env`, `profile/*` (except the `*.example.*` templates), `applications/`, and `data/` (database, HR contact lists, sent-email logs).
