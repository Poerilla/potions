# Cost And Runway Plan

Target raise: **about $145,000** for a CTA-registration-first 12-month build/test runway.

| Category | Basis | Amount |
| --- | --- | --- |
| Founder development stipend | $3,000/month x 12 months | $36,000 |
| Segregated MNQ research/test capital | Held as strategy test capital | $50,000 |
| Databento live data estimate | $179/month x 12 months | $2,148 |
| StoneX simulation software | $49.95/month x 12 months, per provided fee schedule | $599 |
| Cloud/runtime/monitoring | EC2, logs, alerts, backups | $2,000 |
| Broker/API/exchange/commission/slippage allowance | StoneX commissions, exchange/regulatory fees, wires, and slippage buffer | $10,000 |
| NFA/Series 3/registration admin | Series 3, Form 7-R, AP/principal, CTA dues, fingerprint/admin buffer | $2,500 |
| CTA disclosure/legal/compliance/audit reserve | CTA registration-first counsel, disclosure document, NFA review responses, audit/accounting setup | $30,000 |
| Contingency | Unexpected data, infrastructure, and compliance costs | $10,000 |

Planned budget total: **$143,247**.

## Regulatory Cost Assumptions

The registration budget separates official NFA-style fees from planning reserves. The disclosure/legal/compliance/audit reserve is intentionally larger than the hard filing fees because a usable CTA package needs counsel review, disclosure drafting, NFA response time, recordkeeping setup, and accounting/audit structure before any client-facing trading activity.

| Item | Assumption | Source |
| --- | --- | --- |
| NFA CTA Form 7-R application fee | $200 | NFA CTA registration requirements |
| NFA CTA initial/annual dues | $750 | NFA Membership Dues and Fees |
| Principal/AP application fee | $85 | NFA CTA registration requirements |
| Series 3 exam fee | $140 | NFA proficiency/exam guidance |
| CTA disclosure/legal/compliance/audit reserve | $30,000 | Planning reserve based on attached CTA/CTC cost note; counsel quote required |

## StoneX Fee Schedule Assumption

The following table uses the StoneX One fee schedule supplied by the founder for this draft. It has not been independently verified inside a live StoneX account, so counsel/account-opening review should confirm it before funding.

| Item | Provided Schedule |
| --- | --- |
| Retail brokerage account minimum | $2,000 baseline |
| Live simulation account minimum | $5,000 baseline |
| Standard futures contracts | $1.29 per side, per contract |
| Micro futures contracts | $0.50 per side, per contract |
| StoneX Futures Platform | Free |
| Mobile app trading | Free |
| Simulation software | $49.95/month |
| Domestic / international outbound wire | $25 / $50 |
| ACAT transfer out | $125 |
| Inactive account fee | $100/year |
| Margin debit rate | WSJ Call Money Rate + 2.50% |

## StoneX Commission Estimate For Current Models

The replay engine already embeds a **$1.50 per closed-unit audit fee**. The table below compares that embedded audit fee to StoneX commission-only estimates using the supplied per-side rates. Exchange, NFA, clearing, market-data, margin-interest, wire, and slippage costs are not included in these commission-only rows.

| System | Closed Units | StoneX Commission | Model Audit Fee | Delta |
| --- | --- | --- | --- | --- |
| NQ Prior-Opposed Gated Intraday System | 2,160 | $5,573 | $3,240 | $2,333 |
| MNQ Prior-Opposed Gated Intraday System | 2,140 | $2,140 | $3,210 | $-1,070 |
| NQ Ungated Intraday Breakout System | 6,900 | $17,802 | $10,350 | $7,452 |
| MNQ Ungated Intraday Breakout System | 6,886 | $6,886 | $10,329 | $-3,443 |

## Runway Milestones

| Month | Milestone | Required Evidence |
| --- | --- | --- |
| 1 | CTA counsel kickoff and runtime hardening | Structure memo, source manifest, reproducible research package |
| 2 | Series 3 / NFA ORS readiness and live-data shadow mode | Exam/admin plan, stored live bars, no-trade signal reports |
| 3 | Disclosure document draft and broker-paper adapter | Draft disclosure outline, broker order ids mapped to local intents |
| 4 | MNQ broker-paper trial | Daily reports, slippage/cost audit, incident log |
| 5 | CQG/StoneX demo hardening and NFA response reserve | Account/order reconciliation, restart drill, emergency flatten drill |
| 6 | First readiness review | Feed integrity report, order sequencing audit, regulatory gap list |
| 7 | Extended MNQ funded-paper or small-live continuation | Stable reports, variance-to-replay audit, risk-limit adherence |
| 8 | Ungated v2b paper comparison | Secondary system replay-vs-paper evidence and operational differences |
| 9 | Reporting and investor portal draft | Monthly packet, exposure report, drawdown explanation template |
| 10 | Robustness and regime review | QQQ comparison refresh, bad-market behavior, filter review |
| 11 | Compliance/accounting package | Counsel checklist, hypothetical-performance language, recordkeeping plan |
| 12 | Final go/no-go and tier decision | Pilot report, registration/disclosure status, NQ tier decision only after MNQ evidence |

## Capital Treatment

- The **$50,000 MNQ research/test capital** should be segregated from development spend.
- The NQ tier is not funded in this first runway; it remains a future tier after MNQ operations are stable.
- The MNQ test capital is internal research/test capital unless counsel confirms a compliant managed-account or advisory structure.
- Any client trading funds require CTA registration or a confirmed exemption, accepted disclosure/account documents if required, and broker/account approvals before acceptance.
- Canadian CTC/cross-border registration is not included in the base raise; it should be separately scoped if Canadian client activity is pursued.

## Operating Cost Notes

- Databento live data is estimated from the current internal spec at $179/month; commercial/non-display classification can raise the actual cost.
- StoneX account minimums and fee schedule should be confirmed inside the account-opening paperwork before live use.
- Broker/API/exchange fees must be confirmed inside the broker and data-provider portals before live use.
- Development stipend is included because the platform requires real engineering work: data ingest, order routing, reconciliation, reporting, deployment, monitoring, and documentation.