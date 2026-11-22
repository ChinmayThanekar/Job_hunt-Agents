---
name: ats-scanner-and-search
description: >-
  Multi-board job discovery and Gemini match scoring skill. Use when searching for jobs
  across Greenhouse, Lever, Ashby, Workday, LinkedIn, Wellfound, YC Work at a Startup,
  Indeed, and Naukri, or when scoring job descriptions against the candidate profile.
---

# Multi-Board ATS Job Scanner & Match Scorer

## Targeted Search Dorks & Direct APIs

When scouting jobs, combine direct ATS API fetching (`python scripts/job_scout.py`) with targeted `search_web` queries for freshly posted roles:

### 1. Direct ATS Portals (Highest Conversion)
- **Greenhouse**: `site:boards.greenhouse.io "<role>" "<location or remote>"`
- **Lever**: `site:jobs.lever.co "<role>" "<location or remote>"`
- **Ashby**: `site:jobs.ashbyhq.com "<role>" "<location or remote>"`
- **Workday**: `site:myworkdayjobs.com "<role>" "<location or remote>"`

### 2. Startup & High-Growth Networks
- **YC Work at a Startup**: `site:workatastartup.com "<role>"`
- **Wellfound**: `site:wellfound.com/jobs "<role>"`

### 3. Major Job Aggregators
- **LinkedIn Jobs**: `site:linkedin.com/jobs/view "<role>" "<location>"`
- **Naukri / Indeed**: `site:naukri.com/job-listings "<role>"` or `site:indeed.com/viewjob "<role>"`

## Scoring Rubric (`0–100%`)
Use Gemini (`gemini-2.5-flash`) via `scripts/job_scout.py` or evaluate directly using:
1. **Role & Seniority Fit (`0–35 pts`)**: Title match and YoE alignment (`candidate.years_of_experience`).
2. **Technical Stack Overlap (`0–35 pts`)**: Match against `skills.primary` and `skills.secondary`.
3. **Location / Work Mode / Visa (`0–15 pts`)**: Matches `target_preferences.locations` and `work_modes`.
4. **Compensation & Stage (`0–15 pts`)**: Meets minimum compensation and preferred company stage.

## Commands
- Fetch & score live jobs from configured ATS boards and public feeds:
  ```powershell
  python scripts/job_scout.py --scan-all
  ```
- Add a job discovered via `search_web` or browser:
  ```powershell
  python scripts/tracker.py add-job --company "Stripe" --title "Backend Engineer" --location "Bengaluru / Remote" --url "https://boards.greenhouse.io/..." --portal "Greenhouse" --score 88 --description "..."
  ```
