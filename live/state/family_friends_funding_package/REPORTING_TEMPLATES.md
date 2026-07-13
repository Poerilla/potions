# Reporting Templates

These templates are inspired by the sample CTA equity and position workbooks in `data/CTA Samples/`. They are written as Markdown shapes first; they can later become CSV/XLSX/PDF reports.

## Monthly Investor Summary

| Field | Value |
| --- | --- |
| Account / Tier |  |
| Beginning Equity |  |
| Ending Equity |  |
| Net P&L |  |
| Monthly Return |  |
| Year-To-Date Return |  |
| Max Month Drawdown |  |
| Intrabar Stress Drawdown |  |
| Fees / Commissions / Data Allocations |  |
| Open Positions At Month End |  |
| Operational Incidents |  |
| Continue / Pause / Review Decision |  |

## Equity And Margin Status

| Date | Account | Tier | Start Balance | Net Liquidation Value | Initial Margin | Margin Excess | Percent Margin Excess | Notes |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| YYYY-MM-DD | Example | Mini |  |  |  |  |  |  |

## Daily Equity Summary

| Date | Beginning Equity | Ending Equity | Day P&L | Day Return | Month Return | Year Return | Drawdown | Reconciled? |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| YYYY-MM-DD |  |  |  |  |  |  |  |  |

## Position / Exposure Summary

| Date | Strategy | Instrument | Direction | Contracts | Entry Time | Exit Time | Realized P&L | Broker Order IDs Present? | Local/Broker Position Match? |
| --- | --- | --- | --- | ---: | --- | --- | ---: | --- | --- |
| YYYY-MM-DD |  |  |  |  |  |  |  |  |  |

## Execution Fidelity Report

| Check | Pass/Fail | Count | Notes |
| --- | --- | ---: | --- |
| Live bars persisted |  |  |  |
| End-of-day replay matched live signals |  |  |  |
| Broker order ids mapped to local intents |  |  |  |
| Broker/local position mismatches |  |  |  |
| Missed EOD flatten events |  |  |  |
| Stale-feed entry blocks |  |  |  |
| Manual interventions |  |  |  |
| Unexpected orders/fills |  |  |  |

## Monthly Cost Report

| Cost Type | Amount | Notes |
| --- | ---: | --- |
| Market data |  |  |
| Broker/API/exchange fees |  |  |
| Commissions |  |  |
| Slippage estimate |  |  |
| Cloud/runtime |  |  |
| Legal/compliance/accounting |  |  |