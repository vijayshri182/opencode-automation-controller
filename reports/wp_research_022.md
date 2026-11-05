# WP-RESEARCH-022 — First Simple Recruiter Discovery POC (Wibmo)

Date: 2026-11-04
Repository: `C:\Vijay_GitHub\opencode-automation-controller` (branch `master`, no commits; all untracked)
Mode: DEV only; single-job recruiter discovery through the existing controller research interface.
No AI Career Agent DB writes, no candidate/job association changes, no emails, no commits/pushes.

---

## 1. Executive summary and verdict

**Verdict: PARTIAL** — Research completed successfully and is persisted in the controller with source-backed
findings and publicly verified email evidence. However, the target vacancy is **closed (HTTP 410 Gone)**
and no vacancy-specific recruiter email was found; all public emails are **ADJACENT** (company-level). This
is the expected outcome for a closed vacancy and is not a pipeline failure.

---

## 2. Wibmo job details

- Company: Wibmo Inc. (PayU Digital Labs Pvt Ltd; acquired by PayU/Naspers 2019)
- Title: Director Engineering
- Internal job ID: `feb19c33-8495-4db0-ba6c-55219a06cd39`
- External job ID: `1155089474`
- Location: Bangalore, Karnataka, India
- Source URL: https://www.adzuna.in/details/1155089474?utm_medium=api&utm_source=7c7b3ef1
- P1 eligibility: score 91.6, WP-88 ELIGIBLE, VERIFIED status.

---

## 3. Vacancy availability findings

- The Adzuna listing `https://www.adzuna.in/details/1155089474` returns **HTTP 410 (Gone)** as of the
  research date (4 Nov 2026). The webfetch tool captured this as a completed tool call with an error
  (`StatusCode: non 2xx status code (410 GET ...)`), which is persisted in the evidence.
- No identical mirror of internal ID `feb19c33-8495-4db0-ba6c-55219a06cd39` / external ID `1155089474`
  was found on other boards, PayU careers (`careers.payu.in`) or the Accel Wibmo board.
- JobsMap reports no open roles at Wibmo as of 2 Nov 2026.
- **Conclusion: this specific vacancy is not publicly available (likely closed/filled).**
- Related but distinct/inactive Director of Engineering postings exist on Cutshort (via Zyoin, posted
  25 Nov 2020; and a separate "Director Engineering" posted by Shirin AM). These are NOT the same
  vacancy and are not treated as such.

---

## 4. Recruiter / contact findings

Company-level recruiter / talent-acquisition contacts (NOT vacancy-specific — the vacancy is closed):

- **Prabhat Kumar** — Talent Acquisition Manager, Wibmo (oversees tech/product hiring incl. directors).
  LinkedIn: https://linkedin.com/in/prabhat-kumar-3b982991. (Company-level recruiter evidence.)
- **Md A.** — Associate Director, Talent Acquisition at PayU (hires senior sales leaders for PayU
  Digital Labs/Wibmo). LinkedIn: https://linkedin.com/in/amimahmad. (Company-level, sales-focused.)
- **Shirin AM** — former Sr. Executive HR at Wibmo (Nov 2017–Dec 2021); posted "Director Engineering"
  at Wibmo on Cutshort. Now Deputy Manager TA at Paytm/Odessa. (Historical company-level recruiter
  evidence.)
- **Rakesh Ranjan / Zyoin Group** — co-founder & COO; posted "Director of Engineering" at Wibmo via
  Zyoin on Cutshort (25 Nov 2020). LinkedIn: https://linkedin.com/in/rakeshranjanzyoin. (Agency
  recruiter; vacancy-specific linkage to the Adzuna ID unconfirmed.)
- **divya Barathi** — listed as Wibmo team member on Cutshort; no public email/LinkedIn found.
  (Limited evidence.)

General product/leadership contacts (not recruiters):

- **Alias Varghese** — VP & Head of Engineering, Wibmo. LinkedIn: https://linkedin.com/in/aliasvm.
  Wibmo leadership page: https://wibmo.com/leadership.
- **Shailesh Paul** — CEO, Wibmo.
- Company LinkedIn: https://www.linkedin.com/company/wibmo.

Official company careers & contact info:
- Careers: https://www.wibmo.co/careers ; footer "Discover Jobs" on https://wibmo.com
- Contact form: https://wibmo.com/contact/ and https://wibmo.com/contact-us (no direct email on page)
- PayU careers (Wibmo roles): https://careers.payu.in
- Accel Wibmo board: https://jobs.accel.com/companies/wibmo-2

---

## 5. Verified email evidence

All public emails are **ADJACENT** (company-level). No **DIRECT** (vacancy-specific) email exists
because the vacancy is closed.

| Email | Source URL | Supporting excerpt | Evidence date | Evidence type | Vacancy relevance | Confidence | Classification |
|---|---|---|---|---|---|---|---|
| sales@wibmo.com | https://wibmo.com/blogs/beyond-otps-why-indias-new-biometric-authentication-standards-are-the-future-of-digital-payments/ ; https://wibmo.com/blogs/wp-content/uploads/2026/03/Brochure_RBA.pdf | "To know more, write to us at sales@wibmo.com." / "Email: sales@wibmo.com" | 2026-02-09 (blog); 2026-03-13 (brochure) | Official company blog/brochure | ADJACENT (general sales contact) | High | ADJACENT |
| pr@wibmo.com | https://www.prnewswire.com/in/news-releases/wibmo-inc-launches-wibmo-one-step-authentication-and-payment-solution-for-online-and-mobile-payments-591838811.html | "For further details please contact: sales@Wibmo.com or pr@Wibmo.com." | 2016-08-31 | Press release | ADJACENT (PR contact) | High | ADJACENT |
| pkumar@wibmo.co | https://contactout.com/Prabhat-Kumar-326573457 | "To contact Prabhat Kumar send an email to p.kumar343.pk@gmail.com or pkumar@wibmo.co." | Page states most updated found in 2025 | Third-party contact aggregator | ADJACENT (TA Manager; not tied to this vacancy) | Medium | ADJACENT |
| p.kumar343.pk@gmail.com | https://contactout.com/Prabhat-Kumar-326573457 | Same as above | Page states most updated found in 2025 | Third-party contact aggregator | ADJACENT (personal email of TA Manager) | Medium | ADJACENT |
| rakesh@zyoin.com | https://contactout.com/Rakesh-Ranjan-40394065 | "To contact Rakesh Ranjan send..." | Page states most updated found in 2025 | Third-party contact aggregator | ADJACENT (agency recruiter; vacancy linkage unconfirmed) | Medium | ADJACENT |

No email is vacancy-specific (DIRECT). No email was guessed. All emails are backed by public sources.

---

## 6. Direct versus adjacent contact classification

- **DIRECT (vacancy-specific recruiter):** None. The vacancy is closed (410 Gone) and no public source
  ties a specific recruiter to this requisition.
- **ADJACENT (company-level recruiter/TA):** Prabhat Kumar (TA Manager), Md A. (Associate Director
  TA, PayU), Shirin AM (former Sr. Executive HR), Rakesh Ranjan/Zyoin (agency recruiter), divya
  Barathi (limited evidence), plus company contact emails (sales@, pr@).
- **UNCONFIRMED:** Any contact without a verifiable public email or current-employment evidence.

No ADJACENT or UNCONFIRMED contact is treated as vacancy-assigned or outreach-eligible.

---

## 7. Research task and OpenCode session IDs

- Research task ID: `res-f259a8bc2ff8`
- Idempotency key: `wp-research-022-wibmo`
- OpenCode session ID: `ses_e5a493535ffe1DluE499a0K1wn`
- Selected model: `opencode-go/beam-free` (providerID `opencode-go`, modelID `beam-free`)
- Agent: `research` (research_mode=True, deny-all + websearch/webfetch allowlist)
- Task completion status: `completed`
- Non-empty result: yes (4110 chars)
- Evidence item count: 11 (1 webfetch with 410 error + 10 websearch)
- Source URLs: present in evidence and final output
- Idempotency behaviour: verified — duplicate submit returned `{"duplicate": true, "status": "completed"}`
  with the same `research_id`; no second execution.

---

## 8. Model and tool-call summary

- Model: `opencode-go/beam-free` (provider `opencode-go`, model `beam-free`).
- Agent: `research` (isolated, deny-all baseline, websearch + webfetch only).
- Tool calls: 11 total — 1 × `webfetch` (status: error, HTTP 410 Gone) + 10 × `websearch` (all
  completed, no errors).
- No `bash`/`write`/`edit`/`read`/`glob`/`grep`/`list`/`task`/`todowrite` invoked.
- Duration: 73.81 s. Polls: 34 (bounded, 4 s interval, 180 s deadline).
- Tokens: total 74389 (input 7595, output 1124, reasoning 1734). Cost: 0.
- Assistant error: null. Empty output: false. Timed out: false.
- Provider error in serve.err.log: none (no quota errors).

---

## 9. Source URLs and excerpts

See the final output above (§5 email table and §4 contact list). Key sources:

- Adzuna (410): https://www.adzuna.in/details/1155089474?utm_medium=api&utm_source=7c7b3ef1
- Wibmo blog: https://wibmo.com/blogs/beyond-otps-why-indias-new-biometric-authentication-standards-are-the-future-of-digital-payments/
- Wibmo brochure: https://wibmo.com/blogs/wp-content/uploads/2026/03/Brochure_RBA.pdf
- PR Newswire: https://www.prnewswire.com/in/news-releases/wibmo-inc-launches-wibmo-one-step-authentication-and-payment-solution-for-online-and-mobile-payments-591838811.html
- ContactOut (Prabhat Kumar): https://contactout.com/Prabhat-Kumar-326573457
- ContactOut (Rakesh Ranjan): https://contactout.com/Rakesh-Ranjan-40394065
- Wibmo leadership: https://wibmo.com/leadership
- Wibmo careers: https://www.wibmo.co/careers
- PayU careers: https://careers.payu.in
- Accel Wibmo board: https://jobs.accel.com/companies/wibmo-2
- LinkedIn (Tarun Arora): https://linkedin.com/in/tarunarora1984
- LinkedIn (Prabhat Kumar): https://linkedin.com/in/prabhat-kumar-3b982991
- LinkedIn (Alias Varghese): https://linkedin.com/in/aliasvm
- LinkedIn (Rakesh Ranjan): https://linkedin.com/in/rakeshranjanzyoin
- LinkedIn (Shirin AM): https://linkedin.com/in/shirin-am (referenced)
- Wibmo company LinkedIn: https://www.linkedin.com/company/wibmo

---

## 10. Persistence and idempotency verification

- Persisted in `bridge.db` (`research_tasks` table): research_id `res-f259a8bc2ff8`, status `completed`,
  session_id `ses_e5a493535ffe1DluE499a0K1wn`, started_at 1793781582.49, completed_at 1793781656.30,
  error null, result_json populated (4110-char output, 11 evidence items, tool names, model info).
- Idempotency: duplicate submit with key `wp-research-022-wibmo` returned
  `{"duplicate": true, "status": "completed"}` with the same `research_id`; no second execution.
- No AI Career Agent DB writes (per task scope: this POC does not claim AI Career Agent JobResearch
  persistence or dashboard integration).
- No candidate/job association changes.

---

## 11. Limitations and recommended next step

### Limitations
- The target vacancy is closed (HTTP 410 Gone); no vacancy-specific recruiter email exists.
- All public emails are ADJACENT (company-level): sales@wibmo.com, pr@wibmo.com, pkumar@wibmo.co,
  p.kumar343.pk@gmail.com, rakesh@zyoin.com.
- No DIRECT (vacancy-specific) email found — expected for a closed vacancy.
- The webfetch of the Adzuna URL returned 410; this is correctly captured as a tool error in the
  evidence, not hidden.
- No AI Career Agent DB persistence or dashboard integration claimed (per task scope).

### Recommended next step
- Use this POC pattern for an open vacancy (e.g., the Comviva Director PM NGAGE CPaaS role,
  LinkedIn 4474132885, which was proven in WP-RESEARCH-009/010) to demonstrate vacancy-specific
  (DIRECT) recruiter email evidence.
- Promote controller evidence into AI Career Agent `RecruiterContact`/`ContactSource` rows via
  `JobResearchService.promote_contacts()` (already implemented and tested).
- No commits or pushes.

---

## Final verdict

**PARTIAL** — Research completed successfully and is persisted in the controller with source-backed
recruiter findings and publicly verified email evidence. However, the target vacancy is closed
(HTTP 410 Gone) and no vacancy-specific (DIRECT) recruiter email was found; all public emails are
ADJACENT (company-level). This is the expected outcome for a closed vacancy and is not a pipeline
failure. The research isolation boundary (deny-all + websearch/webfetch allowlist) held throughout;
no unauthorized tools were invoked; no credential exposure occurred.

### Safety confirmation
- One job only (Wibmo). No candidate ownership changes. No arbitrary job insertion.
- No authentication bypass. No auto-promotion. No email sending or drafting.
- No job applications or resume submissions. No production changes. No credential extraction.
- No commits or pushes. No controller/OpenCode restarts. Existing uncommitted changes preserved.
- Research instance (4098) and controller (8799) left running, healthy, untouched.