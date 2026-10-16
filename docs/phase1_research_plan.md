# GCC Atlas — Phase 1: Research Requirements

Status: **draft v1, 2026-10-16**. No data has been collected yet. Nothing in this
document is a verified fact about any company or policy. Facts are verified in
Phases 3–5.

## 1. Primary user and decisions supported

**User:** an MNC strategy or expansion team deciding where and how to set up or expand a
Global Capability Centre (GCC) in India.

| # | Decision the user is making | Data that supports it |
|---|---|---|
| D1 | Which city should we shortlist? | Peer GCC presence, talent indicators, office cost observations, state incentives |
| D2 | What will set-up cost and what will running it cost? | Setup cost and recurring cost observations, with unit, period, scope and method |
| D3 | Which state incentives could apply, and on what conditions? | Policy text, eligibility, benefit formula, validity dates, status |
| D4 | What must we comply with? | Central and state regulatory requirements, with issuing authority and effective dates |
| D5 | What have comparable companies done? | Verified GCC centres: city, functions, status, dates, scale |
| D6 | How is the India operation usually structured? | Parent → Indian entity relationships, documented only |

## 2. Target scope

**Cities (6):** Bengaluru (KA), Hyderabad (TS), Chennai (TN), Pune (MH), Noida (UP), Gurugram (HR).

**States whose policies matter:** Karnataka, Telangana, Tamil Nadu, Maharashtra, Uttar Pradesh, Haryana, plus central-government rules.

**Initial companies (10):** see `research/company_shortlist.csv`. Selection rule:
1. At least one **official company source** was discovered for an India centre, or several
   independent news sources agree.
2. Together the companies cover all six cities and more than one industry.
3. No company is included because it "probably" has a GCC. Every city in the
   shortlist is marked *candidate* until Phase 5 verifies it.

## 3. Data requirements matrix

Refresh = how often a source should be re-checked after first ingestion.

| Cat | Data item | Why needed | Decision | Preferred sources (tier) | Verification method | Refresh |
|---|---|---|---|---|---|---|
| A | Parent company, centre name, city/state | Shows peer presence | D1, D5 | Company press releases, careers/location pages (1–2); news (6) | Source text must name company **and** city. Official = "Verified — Official"; ≥2 independent news = "Verified — Independent" | Quarterly |
| A | Functions performed | Talent and functional fit | D5 | Company releases (1); news (6) | Quote-level match to the extracted function list | Quarterly |
| A | Status (operating / announced / office / lead) | Avoids counting announced centres as operating | D5 | Inauguration releases (1) vs. announcement news | Status only from explicit wording ("inaugurated", "opens", "will set up") | Quarterly |
| A | Announcement / opening date | Timeline, maturity | D5 | Press release dates (1) | Date of event ≠ publication date. Both are stored | Quarterly |
| A | Investment, headcount, floor area | Scale benchmark | D2, D5 | Company releases (1); news (6) | Store as a claim with unit and as-of date. Conflicts flagged, never averaged | Quarterly |
| B | Parent ↔ Indian entity | Structure precedent | D6 | MCA filings, annual reports, Form 10-K Exhibit 21 (1–2) | Relationship only from a document stating it. **Never from name similarity** | Annually |
| C | Setup costs (deposit, fit-out, IT, legal, registration, hiring, relocation) | Capex estimate | D2 | Govt fee schedules (3); real-estate reports (5); policy capex definitions | Record unit (INR/sq ft, INR/seat, INR flat), scope, building grade, method, period | Semi-annual |
| D | Recurring costs (rent, CAM, utilities, compensation, statutory, etc.) | Opex estimate | D2 | JLL/CBRE/C&W/Vestian (5); statutory rates from govt (3) | Same as C. Rent quoted vs transacted kept separate; psf/month vs psf/year never mixed | Quarterly (rent); on notification (statutory) |
| E | Regulations (labour codes, company law, FEMA, STPI/SEZ, shops & establishments) | Compliance checklist | D4 | Gazette, ministry and state sites (3); law-firm notes (6) for discovery only | Requires official text. Law-firm summaries alone = "Needs review". **Research only, not legal advice** | On amendment; monthly check |
| F | State incentives (policy, eligibility, benefit, dates, process) | Incentive comparison | D3 | State GR/G.O./gazette (3); Big-4 and law-firm summaries (6) for discovery | Benefit amounts only from official text. Statuses: announced, active, expired, potential eligibility. No company-specific "approved" or "received" status without a document | Monthly |
| G | Talent indicators, salary benchmarks, GCC cluster counts | Talent depth | D1 | NASSCOM-Zinnov (4); govt education stats (3); real-estate GCC leasing share (5) | Methodology and period mandatory. No personal data collected | Annually |
| H | Historical observations | Trends | D1, D2 | All of the above | Each observation stores publication date, period described, retrieval date, geography, unit and method. Never overwritten | Continuous |

## 4. Source tiers (priority order)

1. Official company announcements and annual reports
2. Official corporate filings and company websites
3. Central and state government policies and notifications
4. NASSCOM and Zinnov research
5. JLL, CBRE, Cushman & Wakefield, Colliers, Vestian, and other real-estate reports
6. Credible business news, trade press, and law-firm or Big-4 summaries
7. Job postings and directories (discovery only, never proof)

A tier-6 summary of a policy is a **pointer** to the official text, not evidence of its terms.

## 5. Verification rules

* A claim is "Verified — Official" only when the retrieved official document's text
  contains the claimed fact. The stored excerpt and the retrieval hash must show this.
* A URL alone, a search-engine snippet, or a summary produced by an AI search tool
  is **not** evidence. Items found that way stay at status `Discovered`.
* A publication year is never treated as the period the data describes.
* Conflicts are kept side by side and flagged, never reconciled by averaging.

## 6. Environment constraint discovered during Phase 1

On 2026-10-16 this build environment could not fetch any source host:

* Direct HTTPS from the container returned `CONNECT tunnel failed, response 403` for every
  host tested: nasscom.in, news.microsoft.com, sec.gov, karnataka.gov.in, mca.gov.in and wikipedia.org.
* The WebFetch tool returned `getaddrinfo ENOTFOUND` for news.microsoft.com,
  itbtst.karnataka.gov.in and indianpharmapost.com.
* Only web search worked. It was used **for discovery only**: to find candidate URLs.
  Nothing it returned is recorded as a fact.

Fetching, extraction and verification (Phase 3 onward) are therefore **blocked**
until the environment's network policy allows the source hosts. See
`docs/phase2_report.md`.
