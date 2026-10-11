# Campus — TAM / SAM / SOM Analysis

*Prepared for valuation and go-to-market planning. All figures USD, 2025 baseline. Sources cited inline.*

---

## Market Definitions

| Term | Definition for Campus |
|------|------------------------|
| **TAM** (Total Addressable Market) | Every licensed daycare, preschool, and K–12 school (public + private) in Canada & US that could use an on-premise, compliance-first management system. |
| **SAM** (Serviceable Addressable Market) | Subset of TAM that fits Campus's *current* product shape: single-site, Windows-on-premise, English/French, daycare→small secondary (≤1,500 students), no multi-district SaaS tier yet. |
| **SOM** (Serviceable Obtainable Market) | Realistic 3–5 year capture given solo-founder sales capacity, no brand, on-premise friction, and pilot-first motion. |

---

## 1. Daycare / Childcare Segment (Core Beachhead)

### Market Data (2024–2025)

| Metric | Value | Source |
|--------|-------|--------|
| Global daycare management software (2023) | $9.0B | Research and Markets, Nov 2024 |
| Global daycare management software (2025) | $9.54B | Verified Market Research, Aug 2026 |
| North America share | 41–43% | Research and Markets / VMR |
| North America daycare software (2025) | **$3.9B–$4.1B** | Derived |
| CAGR (2023–2028) | 6.9–7.2% | Research and Markets / VMR |
| Cloud vs on-premise split (2023) | 64% cloud / 36% on-premise | Research and Markets |

### Facility Counts (NA)

| Type | US | Canada | Total |
|------|-----|--------|-------|
| Licensed childcare centers | ~115,000 | ~12,000 | **~127,000** |
| Family/home-based (licensed) | ~95,000 | ~8,000 | **~103,000** |
| **Total licensed facilities** | **~210,000** | **~20,000** | **~230,000** |

*Sources: Child Care Aware of America 2023; Statistics Canada 2023; NARA licensing data.*

### TAM / SAM / SOM — Daycare

| Layer | Calculation | Value |
|-------|-------------|-------|
| **TAM** (all licensed centers, NA) | 230,000 sites × $1,200/yr avg spend | **$276M/yr** |
| **SAM** (centers ≤200 children, English/French, willing on-premise) | 230,000 × 60% size fit × 35% on-premise/open × 80% language | **$39M/yr** |
| **SOM** (3-yr, solo founder, pilot-led) | 150 sites × $1,200/yr | **$180K/yr** (Year 3) |

> **Assumptions**: $100/mo/site avg (flat or per-child ~$1–$2); 60% of centers ≤200 kids; 35% prefer/have on-premise mandate (gov, military, indigenous, privacy-conscious); 80% EN/FR; 150 sites = 50 pilots → 50 paying → 50 referrals over 3 yrs.

---

## 2. K–12 School Segment (Expansion)

### Market Data (2024–2025)

| Metric | Value | Source |
|--------|-------|--------|
| Global K–12 SIS market (2024) | $7.77B–$15.33B | WiseGuyReports / MarketsandMarkets |
| Global K–12 School Mgmt Software (2025) | $6.22B | WiseGuyReports, Aug 2026 |
| North America share (K–12) | ~32% | WiseGuyReports |
| North America K–12 software (2025) | **$2.0B–$4.9B** | Derived |
| CAGR (2025–2035) | 6.4–7.2% | WiseGuyReports |

### School Counts (NA)

| Type | US | Canada | Total |
|------|-----|--------|-------|
| Public K–12 schools | ~98,000 | ~15,500 | **~113,500** |
| Private K–12 schools | ~30,000 | ~2,500 | **~32,500** |
| **Total K–12 schools** | **~128,000** | **~18,000** | **~146,000** |

*Sources: NCES 2023; Statistics Canada 2023; CAPE private school survey.*

### TAM / SAM / SOM — K–12

| Layer | Calculation | Value |
|-------|-------------|-------|
| **TAM** (all K–12, NA) | 146,000 schools × $3,500/yr avg SIS spend | **$511M/yr** |
| **SAM** (small schools ≤1,500 students, single-site, on-premise OK) | 146,000 × 70% size fit × 20% on-premise/open × 85% language | **$87M/yr** |
| **SOM** (5-yr, post-daycare traction) | 75 schools × $3,500/yr | **$262K/yr** (Year 5) |

> **Assumptions**: $290/mo/school avg (SIS + modules); 70% of schools ≤1,500 students; 20% on-premise mandate or preference (rural, indigenous, religious, gov); 85% EN/FR; 75 schools = slower, longer sales cycle.

---

## 3. Combined TAM / SAM / SOM

| Layer | Daycare | K–12 | **Combined** |
|-------|---------|------|--------------|
| **TAM** | $276M | $511M | **$787M/yr** |
| **SAM** | $39M | $87M | **$126M/yr** |
| **SOM (Yr 3)** | $180K | — | **$180K/yr** |
| **SOM (Yr 5)** | $450K | $262K | **$712K/yr** |

---

## 4. Pricing Model Assumptions

| Tier | Target | Pricing | Rationale |
|------|--------|---------|-----------|
| **Daycare Starter** | ≤50 children | $79/mo flat | Below Brightwheel/Procare per-child; simple |
| **Daycare Standard** | 51–150 children | $149/mo flat | Flat = predictable, beats tiered |
| **Daycare Plus** | 151–300 children | $249/mo flat | Caps at ~$0.83/child |
| **School Standard** | ≤500 students | $299/mo flat | Includes grades, scheduling, portal |
| **School Plus** | 501–1,500 students | $499/mo flat | Full module suite |
| **Multi-site / HQ** | Future | TBD | Requires `deployment_mode: HEADQUARTERS` |

> **Note**: Campus's on-premise model = no per-child marginal cost. Flat pricing is a *strategic wedge* against per-child SaaS pricing (Brightwheel ~$1.50–$3.00/child/mo; Procare flat but higher base).

---

## 5. Revenue Build (Conservative)

| Year | Daycare Sites | School Sites | ARR |
|------|---------------|--------------|-----|
| Y1 | 5 (pilots) | 0 | $6K |
| Y2 | 25 | 2 | $54K |
| Y3 | 60 | 8 | **$180K** |
| Y4 | 100 | 25 | $348K |
| Y5 | 150 | 50 | **$712K** |

> At $712K ARR (Yr 5), SaaS comparable multiples (5–8x) → **$3.5M–$5.7M valuation**. With on-premise discount (2–3x) → **$1.4M–$2.1M**. Strategic premium for compliance moat → **+30–50%**.

---

## 6. Key Sensitivities

| Variable | Base | Bear | Bull |
|----------|------|------|------|
| Daycare attach rate (SAM→SOM) | 0.4% | 0.15% | 1% |
| School attach rate | 0.3% | 0.1% | 0.8% |
| Avg price/daycare | $149/mo | $99/mo | $199/mo |
| Avg price/school | $399/mo | $249/mo | $599/mo |
| Sales cycle (months) | 6 / 12 | 9 / 18 | 3 / 6 |
| Churn (annual) | 8% | 15% | 5% |

---

## 7. Sources Summary

| # | Source | Date | Key Figures Used |
|---|--------|------|------------------|
| 1 | Research and Markets: *Daycare Management Software Global Market Opportunities and Strategies to 2033* | Nov 2024 | $9B (2023), 43% NA, 6.9% CAGR, 64% cloud |
| 2 | Verified Market Research: *Daycare Software Market* | Aug 2026 | $9.54B (2025), 41% NA, 6.0% CAGR |
| 3 | Technavio: *Childcare Management Software Market 2024–2028* | Aug 2024 | $82M growth, 7.16% CAGR, 35% NA |
| 4 | WiseGuyReports: *K-12 Student Information System Market* | Jun 2026 | $8.27B (2025), 6.4% CAGR |
| 5 | WiseGuyReports: *K-12 School Management Software Market* | Aug 2026 | $6.22B (2025), 7.2% CAGR, $2.0B NA |
| 6 | MarketsandMarkets: *Student Information System Market to 2029* | Oct 2024 | $15.33B (2024), 15.9% CAGR |
| 7 | Grand View Research: *Student Information System Market* | 2026 | $14.0B (2025), 13.7% CAGR |
| 8 | NCES / Child Care Aware / Statistics Canada | 2023 | Facility/school counts |
| 9 | Procare vs Brightwheel competitive guides | 2026 | Pricing models, flat vs per-child |

---

## 8. Narrative for Investors

> **TAM ($787M)** is the *theoretical ceiling* if every licensed daycare and K–12 school in NA bought Campus. Not credible as a near-term number.
>
> **SAM ($126M)** is the *addressable slice* given Campus's current on-premise, single-tenant, English/French, ≤1,500-student product. This is the market you can *actually sell to today* without building SaaS, multi-site, or new languages.
>
> **SOM ($712K ARR by Year 5)** is the *realistic capture* given solo-founder sales, pilot-first motion, 6–12 month cycles, and no brand. It assumes 225 total sites (150 daycare + 75 schools) at blended ~$260/mo.
>
> **The wedge**: Flat pricing + on-premise + compliance-first (PIPEDA/CCEYA/FERPA/COPPA/PHIPA/FIPPA) beats cloud incumbents for privacy-mandated buyers. The *expansion* is multi-site HQ mode + SaaS tier + district sales — each unlocks a new SAM layer.

---

*All figures are estimates for planning. Validate with primary research (surveys, pilot conversations) before formal use.*