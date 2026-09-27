# Engineering Contract

This document formalizes the binding engineering rules and quality standards for the **Personal Job Intelligence Platform**.

---

## 1. Core Principles

1. **Accuracy over volume**: Better to present 5 confirmed, high-fit jobs than 50 outdated or mismatched listings.
2. **Never invent data**: If a company, salary range, requirement, or contact is not present in the verified source, it must never be generated or assumed.
3. **Never fabricate URLs**: All job postings and application URLs must originate from actual network responses and pass HTTP verification.
4. **Never fabricate recruiters**: Recruiter profiles must come from real public profile discoveries with explicit source links.
5. **Never silently assume a job is active**: Every job must undergo an explicit status verification check before report generation.
6. **Never silently assume a LinkedIn/social profile is relevant**: Profile matching must provide explicit relevance rationales and confidence scores.
7. **Never use Google Sheets as the only database**: Sheets is an operational UI dashboard, not a resilient datastore.
8. **PostgreSQL is the system of record**: All data mutations, audit trails, and states persist in PostgreSQL.
9. **Google Sheets is the operational dashboard**: Published views are downstream projections of the PostgreSQL system of record.
10. **AI is not the source of truth for URL/status verification**: Deterministic HTTP network requests and status codes govern URL liveness, never LLM hallucination.
11. **All AI output must be structured and validated**: Every LLM call must be parsed through strict Pydantic schemas. Unparseable responses are rejected.
12. **External sources must be accessed legally and within their technical restrictions**: Respect `robots.txt`, rate limits, and public API terms.
13. **Never bypass CAPTCHA, authentication, paywalls, anti-bot protections, or access controls**: If a target requires authorization or blocks scrapers, log and bypass gracefully.
14. **Build observable and testable components**: Every module must have structured logging, metric hooks, and comprehensive unit/integration tests.
15. **Every phase must have explicit verification**: No phase advances until test verification and live endpoint validation are documented.
16. **Do not proceed automatically to the next phase**: Explicit user sign-off is mandatory between phases.

---

## 2. Hard System Constraints

* **Strictly Manual Application**: The system must **NEVER** automatically submit job applications, auto-fill external application forms, or send unsolicited emails on behalf of the user. The user applies manually.
* **Multi-Profile Isolation**: Each resume represents an independent profile with its own criteria, match history, and dedicated Google Sheet tab/dashboard.
* **Deterministic Verification**: Liveness and status validation must precede every daily report pass.
