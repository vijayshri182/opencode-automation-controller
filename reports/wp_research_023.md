# WP-RESEARCH-023 — Open Vacancy Recruiter Discovery and AI Career Agent Promotion POC

Date: 2026-11-04
Repository: `C:\Vijay_GitHub\opencode-automation-controller` (controller side) + AI Career Agent (read-only, no writes)
Mode: DEV only; live research via controller (authorized, no service restarts); no AI Career Agent DB writes.

---

## 1. Vacancy verification (Phase 1)

- **Vacancy URL:** https://in.linkedin.com/jobs/view/director-product-management-ngage-cpaas-at-comviva-4474132885
- **Status:** **OPEN / currently posted.** LinkedIn public page shows "Director - Product Management (NGAGE CPaaS)" at Comviva, Bengaluru, Karnataka, India, "1 month ago 132 applicants", with full job description, qualifications, seniority (Director), employment type (Full-time), industry (Software Development). The page is accessible and renders the job posting (guest view).
- **Verification timestamp:** 2026-11-04 (UTC) during this task.
- **Source:** LinkedIn public job page (above URL). Cross-referenced with JobLeads aggregator (https://www.jobleads.com/in/job/director-product-management-ngage-cpaas--bengaluru--eadbca7af701cd8a71a39a489a7f8be1f) which shows datePosted 2026-10-14, validThrough 2026-11-13.
- **Conclusion:** vacancy is currently open. Proceeded to research.

---

## 2. Research task and OpenCode session IDs

- **Research task ID:** `res-3cbcf7a958a9`
- **Idempotency key:** `wp-research-023-comviva-director-pm`
- **OpenCode session ID:** `ses_e5a454061ffe5436kZODerPQZJ`
- **Selected model:** `opencode-go/beam-free` (providerID `opencode-go`, modelID `beam-free`)
- **Agent:** `research` (isolated, deny-all + websearch/webfetch allowlist)
- **Task completion status:** `completed`
- **Non-empty result:** yes (4110 chars)
- **Evidence item count:** 13 (1 webfetch + 12 websearch, all status `completed`, no errors)
- **Source URLs:** present in evidence and final output
- **Idempotency behaviour:** verified — duplicate submit returned `{"duplicate": true, "status": "completed"}` with the same `research_id`; no second execution.
- **Duration:** 91.96 s. Polls: 19 (bounded, 4 s interval, 240 s deadline).
- **Tokens:** total 74389 (input 7595, output 1124, reasoning 1734). Cost: 0.
- **Assistant error:** null. Empty output: false. Timed out: false.
- **Provider errors:** none (no quota errors in serve.err.log).

---

## 3. Recruiter evidence and classifications

No recruiter is named on the public LinkedIn job page, and no contact is directly tied to job ID
4474132885. All contacts below are **ADJACENT/UNCONFIRMED** (Comviva TA/product leadership), not
vacancy-specific. DIRECT requires explicit vacancy-specific evidence, which is absent.

| Name | Designation | Company | Profile URL | Public email (directly supported?) | Source URL | Supporting excerpt | Evidence date | Evidence type | Vacancy relevance | Confidence / limitations |
|---|---|---|---|---|---|---|---|---|---|---|
| Bharti Choudhary | Talent Acquisition Manager | Comviva | https://linkedin.com/in/bhartichoudhary | bharti.choudhary1@comviva.com (directly supported by her own LinkedIn posts) | https://linkedin.com/in/bhartichoudhary ; https://humantic.ai/public-profile/bharti-choudhary-ddaa15bf63897636 | "Share profile at bharti.choudhary1@comviva.com"; Humantic: "Frequently posts about and recruits for senior-level and strategic roles at Comviva, including Directors and Heads" | Posts ~1–7 months ago (relative) | Self-published LinkedIn posts + third-party profile | ADJACENT | Medium — TA manager who recruits senior/strategic roles incl. Directors, incl. CPaaS presales/product-adjacent roles; no post specifically for this vacancy |
| Puja Kumari | Talent Acquisition Lead | Comviva (Tech Mahindra) | https://linkedin.com/in/puja-kumari-12281a45 | Not publicly evidenced | https://linkedin.com/in/puja-kumari-12281a45 | "As the Talent Acquisition Lead at Comviva-A Tech Mahindra Company, I am responsible for…" | Posts ~3 months ago (relative) | Self-published LinkedIn profile/posts | ADJACENT | Medium — no email publicly evidenced; no direct tie to vacancy |
| Sweta Pandey | Talent Acquisition Executive | Comviva | https://linkedin.com/in/Sweta-pandey-a61a01238 | sweta.pandey2@comviva.com (directly supported by her own LinkedIn post); Unifers also shows sweta.pandey@comviva.com | https://linkedin.com/in/Sweta-pandey-a61a01238 ; https://unifers.ai/person/sweta-pandey-a61a01238/... | "Interested candidates can DM me or share their CV at sweta.pandey2@comviva.com" | Post ~2 months ago (relative) | Self-published LinkedIn post + third-party aggregator | ADJACENT | Medium — posts hiring for BD/EA roles; not this vacancy; second email from aggregator |
| Amisha Pandey | Technical Recruiter | Comviva | (profile referenced via ContactOut/RocketReach; URL not captured) | amisha.pandey@comviva.com (aggregator-stated, not self-published); also amishabkk@gmail.com, amisha.pandey@gmail.com | https://contactout.com/amisha-pandey-73840 ; https://rocketreach.co/amisha-pandey-email_122254401 | ContactOut: "To contact Amisha Pandey send an email to … amisha.pandey@comviva.com" | Profile last verified July 2026 | Third-party aggregator | ADJACENT/UNCONFIRMED | Medium-low — email from aggregator, not self-published; not vacancy-specific |
| Anam Khan | Assistant Manager Talent Acquisition | Comviva (Tech Mahindra) | Not captured | anam.khan@comviva.com (directly supported via Bharti Choudhary's post) | https://linkedin.com/in/bhartichoudhary | "Please apply..." (truncated in model output) | ~1–7 months ago (relative) | Self-published LinkedIn post (via Bharti Choudhary) | ADJACENT | Medium — TA contact, no direct tie to this vacancy |

### General product/leadership contacts (NOT recruiters)
- **Tarun Arora** — VP Product Management, NGAGE/CPaaS (LinkedIn: https://linkedin.com/in/tarunarora1984). No public email evidenced. Product owner for NGAGE, not TA.
- **Deshbandhu Bansal** — COO, RevTech (Comviva event/press pages). No public email evidenced.
- **Aishwarya Patil** — Senior Product Manager, CPaaS & Network API Platform (LinkedIn: https://linkedin.com/in/productmanageraishwaryapatil). No public email evidenced.
- **Ravi Shankar** — VP, Global Head of Business Development (LinkedIn post source). No public email evidenced.
- **Jiwateshwar Singh** — Head of Product Management (Comviva leadership page). No public email evidenced.
- **Jens Voigt** — Head of Product Management, BlueMarble (Comviva leadership page). No public email evidenced.

### Public professional email addresses
| Email | Source URL | Supporting excerpt | Evidence date | Evidence type | Vacancy relevance | Confidence | Classification |
|---|---|---|---|---|---|---|---|
| bharti.choudhary1@comviva.com | https://linkedin.com/in/bhartichoudhary | "Share profile at bharti.choudhary1@comviva.com" | Posts ~1–7 months ago (relative) | Self-published LinkedIn post | ADJACENT | Medium | ADJACENT |
| sweta.pandey2@comviva.com | https://linkedin.com/in/Sweta-pandey-a61a01238 | "share their CV at sweta.pandey2@comviva.com" | Post ~2 months ago (relative) | Self-published LinkedIn post | ADJACENT | Medium | ADJACENT |
| sweta.pandey@comviva.com | https://unifers.ai/person/sweta-pandey-a61a01238/... | (aggregator) | ~2 months ago (relative) | Third-party aggregator | ADJACENT/UNCONFIRMED | Medium-low | ADJACENT/UNCONFIRMED |
| amisha.pandey@comviva.com | https://contactout.com/amisha-pandey-73840 | "To contact Amisha Pandey send an email to … amisha.pandey@comviva.com" | Profile last verified July 2026 | Third-party aggregator | ADJACENT/UNCONFIRMED | Medium-low | ADJACENT/UNCONFIRMED |
| anam.khan@comviva.com | https://linkedin.com/in/bhartichoudhary | "Please apply..." (truncated in model output) | ~1–7 months ago (relative) | Self-published LinkedIn post (via Bharti Choudhary) | ADJACENT | Medium | ADJACENT |

No emails were guessed. All emails are backed by public sources (self-published LinkedIn posts or
third-party aggregators). None is DIRECT (vacancy-specific) — no contact is directly tied to job ID
4474132885.

### Unavailable / not evidenced
- Named job poster for the LinkedIn listing (guest view did not expose one).
- Any email address directly tied to this specific vacancy (DIRECT).
- Definitive absolute posting date (relative "1 month ago"; JobLeads `datePosted: 2026-10-14`,
  `validThrough: 2026-11-13`).
- Comviva-owned career-portal job ID.

---

## 4. AI Career Agent persistence and promotion results

**Not performed in this task.** Phase 4 of the task requires inspecting existing JobResearchService
and promoting contacts using the supported integration. The AI Career Agent backend is not running
(no health endpoint on 8000/8080/8001/5000), and the task says "Do not start the isolated research
instance unless separately authorized" and "Do not restart ... services." The AI Career Agent backend
is not running. The controller→research E2E was already proven in WP-RESEARCH-010 (PASS) and
WP-RESEARCH-022 (PARTIAL).

The existing implementation is ready:
- `JobResearch` model + migration `j9r0e1s2e3a4` (applied to dev DB in WP-RESEARCH-017).
- `JobResearchService.trigger_research()` + `promote_contacts()` (implemented + tested, 7/7 pass).
- `ResearchControllerClient` (async, bounded retry, no credential logging).
- API endpoints: `POST/GET /api/v1/candidates/{candidate_id}/jobs/{job_id}/research`,
  `POST .../research/retry`.
- Frontend: `job-research-panel.tsx` wired to dashboard.

Persisting this result into AI Career Agent would require: (1) AI Career Agent backend running,
(2) an authenticated user owning a job record for this Comviva vacancy, (3) calling
`POST /api/v1/candidates/{candidate_id}/jobs/{job_id}/research`. None of these are available
without starting the backend (not authorized in this task) and creating a job record (forbidden).
The controller-side research result is persisted in `bridge.db` (research_id `res-3cbcf7a958a9`,
status `completed`, session_id, timestamps, result_json with 13 evidence items).

---

## 5. Idempotency

Verified: duplicate submit with key `wp-research-023-comviva-director-pm` returned
`{"duplicate": true, "status": "completed"}` with the same `research_id` (`res-3cbcf7a958a9`);
no second execution started. No duplicate controller task created.

---

## 6. Tests and limitations

- Controller→research E2E: PASS (this task). Text-only not separately run (web research run included
  both websearch and webfetch). Web research run: 13 tool calls, all completed, no errors, non-empty
  structured result, no timeout, no credential exposure.
- AI Career Agent persistence/promotion: not exercised live (backend not running, no job record).
  Offline tests pass (7/7 integration, 51/51 regression, tsc clean).
- No live E2E through AI Career Agent performed.

---

## 7. Final safety state

- No emails sent, no recruiter messages, no job applications, no resume submissions.
- No production changes, no credential extraction, no authentication bypasses.
- No commits or pushes.
- No service restarts (controller 8799 and research 4098 left running, healthy, untouched).
- AI Career Agent backend not running (not started — not authorized).
- Existing uncommitted changes preserved.
- Secrets not logged or exposed.

## Final verdict

**PARTIAL** — Live controller→research execution succeeded with actual websearch/webfetch tool calls
and produced a structured, evidence-backed result with source URLs, excerpts, classifications and
publicly evidenced emails (all ADJACENT/UNCONFIRMED, since no contact is directly tied to this
vacancy). Idempotency verified. However, AI Career Agent persistence/promotion/dashboard verification
could not be performed (backend not running, no job record for this vacancy). The existing
implementation is ready and offline-tested. The live chain through AI Career Agent remains a separate,
operator-authorized step.

### Recommended next step
Operator authorizes: (1) start AI Career Agent backend, (2) provision the Comviva job record via normal
ingestion (or use an existing job), (3) run the research via `POST /api/v1/candidates/{candidate_id}/
jobs/{job_id}/research` and verify persistence + promotion + dashboard. No commits/pushes. No service
restarts without authorization. No credential changes. No emails.