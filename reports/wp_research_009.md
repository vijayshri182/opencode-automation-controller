# WP-RESEARCH-009 — Isolated OpenCode Go Model and Web Research Validation

Date: 2026-11-04
Repository: `C:\Vijay_GitHub\opencode-automation-controller` (branch `master`, no commits; all untracked)
Mode: DEV only; live isolated research instance on port 4098 (authorized start/stop for this bounded test).
No controller/dev restart, no credential changes, no subscriptions purchased, no commits/pushes.

---

## 1. Preflight evidence

- Controller `http://127.0.0.1:8799/health` → `{"ok": true, "service": "mcp_server"}`.
- Development OpenCode `http://127.0.0.1:4097/global/health` → `{"healthy":true,"version":"1.18.30"}`.
- Port 4098: **FREE** at start of run.
- Research config present: `C:\Users\user\.config\opencode-research\opencode.jsonc`.
- Research workspace present: `C:\Vijay_GitHub\opencode-research-workspace`.
- Model availability (read-only, no credential values exposed): `opencode-go` provider CONNECTED; model
  `beam-free` (`name: "Beam Free"`, `capabilities.toolcall: true`, `input.text: true`, `output.text: true`)
  present in the provider model list. Free `opencode` provider models also listed but are the
  historically quota-blocked tier.

---

## 2. Process and model details

- Research instance PID: **23184** (`opencode serve --port 4098 --print-logs`,
  cwd `C:\Vijay_GitHub\opencode-research-workspace`,
  `OPENCODE_CONFIG=C:\Users\user\.config\opencode-research\opencode.jsonc`, unauthenticated loopback).
- Port: 4098. Version: 1.18.30.
- Effective config re-verified:
  - Server-level permission: deny-all (`* : deny`) with `websearch: allow`, `webfetch: allow`,
    `external_directory: deny`, `bash/write/edit/glob/grep/list/task/todowrite/read: deny`.
  - Agent `research` (`mode: all`) with tools allowlist `websearch: true`, `webfetch: true`, all other
    tools `false`; agent-level permission mirrors deny-all with the two allows.
- Model under test: **`opencode-go/beam-free`** (providerID `opencode-go`, modelID `beam-free`).
  No silent substitution; no other model attempted.
- Evidence logs: `reports/evidence/wp_research_009/serve.out.log`, `serve.err.log`
  (serve.err.log contains **no** `ERROR`/stream-error lines — no provider quota errors).

---

## 3. Session IDs and execution results

### 3.1 Text-only connectivity (Phase 3)
- Session ID: `ses_e5b00d2bbffeoKjvsngM2PHudW`
- Prompt: `Reply with exactly: WP9_TEXT_OK`
- Result: **non-empty assistant text `WP9_TEXT_OK`**, `empty_output: false`, `timed_out: false`,
  elapsed 4.13 s, polls 2, 0 tool calls.
- Assistant metadata: providerID `opencode-go`, modelID `beam-free`, tokens total 3433 (input 1546,
  output 6, reasoning 25), cost 0, error null.

### 3.2 Actual web research (Phase 4)
- Session ID: `ses_e5b00c2b1ffeMcLj92II22iLuq`
- Prompt: bounded read-only research of the Comviva Director – Product Management (NGAGE CPaaS)
  opening in Bengaluru (websearch + webfetch required).
- Result: **non-empty structured final text** (3723 chars), `empty_output: false`, `timed_out: false`,
  elapsed 109.36 s, polls 34, assistant error null.
- Assistant metadata: providerID `opencode-go`, modelID `beam-free`, tokens total 74389
  (input 7595, output 1124, reasoning 1734), cost 0.
- **Actual tool calls (16 total, all status `completed`):**
  - 15 × `websearch` (queries on the Comviva NGAGE CPaaS Director PM role, recruiter talent-acquisition
    contacts, Naukri/LinkedIn/Comviva careers, email evidence, etc.)
  - 1 × `webfetch` (URL: `https://in.linkedin.com/jobs/view/director-product-management-ngage-cpaas-at-comviva-4474132885`,
    retrieved the LinkedIn job page)
  - No `bash`/`write`/`edit`/`read`/`glob`/`grep`/`list`/`task`/`todowrite` invoked.
  - No tool errors (`state.error: null` for all).
- Probe artifact: `reports/evidence/wp_research_009/wp009_probe_results.json`.

---

## 4. Research findings and source URLs (from the live session)

### Job listing
- **Original job listing URL:** https://in.linkedin.com/jobs/view/director-product-management-ngage-cpaas-at-comviva-4474132885
- **Platform job ID:** LinkedIn `4474132885`; Jobleads aggregator ID `eadbca7af701cd8a71a39a489a7f8be1f`
  (https://www.jobleads.com/in/job/director-product-management-ngage-cpaas--bengaluru--eadbca7af701cd8a71a39a489a7f8be1f)
- **No Comviva-owned career-portal job ID found** (unavailable).
- **Job title:** Director - Product Management (NGAGE CPaaS)
- **Company:** Comviva (Comviva Technologies Limited)
- **Location:** Bengaluru, Karnataka, India (on-site)
- **Posting date:** Jobleads schema `datePosted: 2026-10-21`, `validThrough: 2026-11-13`; LinkedIn shows
  relative "~3 weeks ago"/"~1 month ago" (inconsistent across captures) — exact single posting date
  unavailable/ambiguous.
- **Salary (Jobleads only):** INR 400,000–700,000/year.
- **Seniority/Type/Industry:** Director; Full-time; Software Development.

### Publicly evidenced recruiter contacts (Comviva Talent Acquisition)
- **Bharti Choudhary** — Talent Acquisition Manager, Comviva. Email: `bharti.choudhary1@comviva.com`
  (source: LinkedIn post; excerpt "Email resume @ bharti.choudhary1@comviva.com"). Adjacent evidence only
  (posted Enterprise Presales Consultant (CPaaS) and tagged Tarun Arora); not direct evidence for this
  specific role.
- **Anam Khan** — Assistant Manager Talent Acquisition, Comviva. Email: `anam.khan@comviva.com`
  (source: LinkedIn hiring posts; excerpt "share their updated resume at: Anam.khan@comviva.com").
  Adjacent evidence only.
- **Puja Kumari** — Talent Acquisition Lead/Senior Manager, Comviva. Email: `puja.kumari@comviva.com`
  (source: LinkedIn posts; excerpt "Share your CV at puja.kumari@comviva.com"). Adjacent evidence only.
- **Sabyasachi Goswami** — Director Talent Acquisition, Comviva. No Comviva email directly evidenced;
  posts cite `sabyasachi.goswami@netcracker.com` (prior employer) — mark unavailable for Comviva.
- **Sabyasachi G** — Director TA @ Comviva Technologies. No Comviva email evidenced; posts reference
  `zuhi.karn@comviva.com`.
- **Soma Sen** — Sr. Manager, Global TA @ Comviva. No email evidenced.
- **Garima Tripathi, Jaishree Y, Shreshtha Nagar** — listed in Comviva TA team (The Org); no public
  emails found.

### Historical (not current) recruiter contact
- **Venkat A** — former TA Specialist at Comviva (Aug 2021–Jun 2022). Email `venkata.a@comviva.com`
  appears in 2022 post only; treat as historical/outdated.

### General product/leadership contacts (not recruiters)
- **Tarun Arora** — VP Product Management, NGAGE/CPaaS (LinkedIn: https://linkedin.com/in/tarunarora1984).
  No public email evidenced. Product owner for NGAGE, not TA.
- **Deshbandhu Bansal** — COO, RevTech (Comviva event/press pages). No public email evidenced.
- **Aishwarya Patil** — Senior Product Manager, CPaaS & Network API Platform
  (https://linkedin.com/in/productmanageraishwaryapatil). No public email evidenced.
- **Ravi Shankar** — VP, Global Head of Business Development (LinkedIn post source). No public email
  evidenced.
- **Jiwateshwar Singh** — Head of Product Management (Comviva leadership page). No public email
  evidenced.
- **Jens Voigt** — Head of Product Management, BlueMarble (Comviva leadership page). No public email
  evidenced.

### Sources / excerpts
- LinkedIn listing: https://in.linkedin.com/jobs/view/director-product-management-ngage-cpaas-at-comviva-4474132885
  — "1 month ago 132 applicants"; job description and qualifications as quoted.
- Jobleads: https://www.jobleads.com/in/job/director-product-management-ngage-cpaas--bengaluru--eadbca7af701cd8a71a39a489a7f8be1f
  — schema `datePosted: 2026-10-21`, salary INR 400,000–700,000.
- Comviva NGAGE product page: https://www.comviva.com/products-solutions/revtech/communication-platform-as-a-service/
  — NGAGE CPaaS description.
- Comviva leadership/press pages for Tarun Arora, Deshbandhu Bansal, Jiwateshwar Singh, Jens Voigt.
- Comviva TA roster: https://theorg.com/org/comviva/teams/talent-acquisition.

### Unavailable / not evidenced
- Named job poster for the LinkedIn listing (guest view did not expose one).
- Any email address directly tied to this specific role.
- Confirmation that the listed TA contacts are assigned to this requisition.
- Comviva-owned career-portal job ID.

No emails were guessed.

---

## 5. Error logs (if any)

- `reports/evidence/wp_research_009/serve.err.log`: **no ERROR / stream-error lines**. No provider quota
  errors, no model errors, no tool errors. Only INFO-level session lifecycle and
  `stream providerID=opencode-go modelID=beam-free` lines.
- `reports/evidence/wp_research_009/serve.out.log`: 0 bytes (stdout empty; logs go to stderr).

---

## 6. Executor compatibility assessment (Phase 5)

- The existing `ResearchExecutor` (WP-RESEARCH-EXECUTION-001) uses `opencode_research_base_url()`,
  `opencode_research_agent()`, `opencode_research_tools()` from config. It does **not** pin a model;
  `send_prompt_async` is called with `model=None`, letting the server default apply. To use
  `opencode-go/beam-free`, the model must be passed at submit time (the live run above did this via
  the adapter's `send_prompt_async(..., model={"providerID":"opencode-go","modelID":"beam-free"})`).
- The executor can be extended to accept a `model` parameter without weakening isolation, but the
  research config does not pin a model. This is a small, safe enhancement (operator-gated) and was
  **not** applied in this task (no source changes).
- Live executor integration through the controller requires a controller restart (operator-gated) to
  expose the research tools; this remains a separate deployment prerequisite. No controller restart
  was performed.
- The `ResearchExecutor` isolation checks (`research_mode=True` required) and redaction logic are
  unaffected; the model change does not bypass them.

---

## 7. Cleanup verification (Phase 6)

- Research instance PID **23184** stopped (`Stop-Process -Force`); exited.
- Port 4098: **FREE** (no listener).
- Controller `127.0.0.1:8799/health` → `{"ok": true, "service": "mcp_server"}` (untouched, healthy).
- Development OpenCode `127.0.0.1:4097/global/health` → `{"healthy":true,"version":"1.18.30"}` (untouched, healthy).
- Port 4096 listener still present (pre-existing, untouched).
- No credentials modified, no `.env`/config/provider changes, no subscriptions purchased, no commits/pushes.
- Evidence preserved in `reports/evidence/wp_research_009/` (serve.out.log, serve.err.log,
  wp009_probe_results.json).

---

## 8. Final verdict

**PASS** — all acceptance criteria met:
- Successful nonempty text response: **PASS** (text-only run → `WP9_TEXT_OK`, 4.13 s, non-empty).
- Successful actual websearch invocation: **PASS** (15 `websearch` calls, all `completed`, no errors).
- Successful actual webfetch invocation: **PASS** (1 `webfetch` call, `completed`, retrieved the LinkedIn
  job page).
- Structured research output with source evidence: **PASS** (final text 3723 chars with job URL, platform
  job ID, job details, recruiter contacts with emails, general product/leadership contacts, unavailable
  info marked, source URLs and excerpts).
- No unauthorized tools invoked: **PASS** (only `websearch` and `webfetch`; no bash/write/edit/read/glob/
  grep/list/task/todowrite).
- No credential exposure: **PASS** (no secrets in logs/output; auth via existing opencode-go key in
  auth.json; no credential printed or persisted).
- Clean process shutdown: **PASS** (PID 23184 stopped; port 4098 free; controller/dev healthy).

The `opencode-go/beam-free` model successfully bypasses the free-tier quota blocker that affected
`opencode/big-pickle`, `opencode/flint-40b-free`, `opencode/deepseek-v4.1-flash-free` and
`opencode/mimo-v2.6-flash-free` on the isolated research instance. The research isolation boundary
(deny-all + websearch/webfetch allowlist) held throughout.

**Recommended next step:** operator-gated — (1) restart the controller to expose the research MCP tools,
(2) optionally extend `ResearchExecutor` to accept a `model` parameter (defaulting to
`opencode-go/beam-free` or a configured value), (3) run one controlled end-to-end research task through
the controller API and verify `pending → running → completed` with persisted `session_id` and
`result_json` containing actual tool calls. No commits/pushes. No subscription changes. No service
restarts without authorization.