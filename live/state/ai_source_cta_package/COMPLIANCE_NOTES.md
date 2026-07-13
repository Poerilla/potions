# Compliance Notes For Performance Materials

This is a working checklist, not legal advice.

## Current Package Status

- The package contains **simulated/backtested** strategy results.
- It does not contain audited live CTA client performance.
- The external version intentionally omits exact signal formulas, timestamps, and sizing parameters.
- It should not be distributed externally until reviewed by qualified compliance counsel.
- Any external version should place the required hypothetical-performance cautionary language immediately next to performance results, not only on a cover page.

## Official References Checked

- NFA Compliance Rule 2-29, promotional material and hypothetical performance: https://www.nfa.futures.org/rulebooksql/rules.aspx?RuleID=RULE+2-29&Section=4
- CFTC discussion of Rule 4.41 and proximity of hypothetical-performance statements: https://www.cftc.gov/LawRegulation/FederalRegister/FinalRules/e7-3122.html
- NFA promotional material guide: https://www.nfa.futures.org/members/member-resources/files/promo-material-guide.pdf

## Assumptions To Keep With The Tear Sheet

- Model account: $1,000,000 reference capital for return statistics.
- Futures base book: capped NQ intraday campaign unit; exact sizing map retained internally.
- Replay window: 2021-03-04 through 2026-03-06.
- Execution engine: internal order-lifecycle replay.
- Costs: 1-tick adverse slippage on market/stop fills and $1.50 per closed unit in audit.
- Known unresolved issue: tick reconstruction is still required for same-minute and sequence-sensitive campaigns.
