# Start-Small Cloud Bootstrap

## Current Answer

`mnq/case_studies/STRATEGY_TRACKER.md` did not previously call out the
one-contract v2b TP1-only row directly. The detailed plan is in
`live/specs/START_SMALL_BROKER_EXECUTION_PLAN.md`.

The explicit first-stage model is:

- Strategy: `v2b_scaleout`
- Market: `MNQ`
- Sizing: `1/0/0` (`entry_qty=1`, `tp1_qty=1`, `tp2_qty=0`, no runner)
- Entry mode: OCO then reverse
- Replay snapshot: `$10,084.50` net, `-$3,109` intrabar stress DD, `1.11` PF
- Purpose: infrastructure proof, not maximum edge

## Lowest-Stress Alternatives

If the goal is the smallest true `StrategyPlugin` / `Engine` / `PaperBroker`
stress row, the current alternatives are:

| Candidate | Market | Net | Stress DD | Net / Stress | Read |
|---|---:|---:|---:|---:|---|
| Hourly ST + PMC base 50/150 | MYM | $6,051 | -$1,366 | 4.43 | Lowest absolute stress in the current plugin table, but different market/rule family. |
| Hourly ST + PMC close-against-entry | MES | $5,525 | -$2,394 | 2.31 | Low heat, but partial MES coverage and weaker efficiency. |
| Hourly ST + PMC 25/75 3R | MNQ | $10,922 | -$2,462 | 4.44 | Lowest-stress MNQ plugin alternative outside v2b TP1-only. |
| v2b TP1-only `1/0/0` | MNQ | $10,085 | -$3,109 | 3.24 | Best infrastructure rehearsal because it exercises 1m feed, 5m OR logic, OCO, stop fills, and EOD flattening. |

The lower-stress hourly rows are valid research candidates, but v2b remains the
better first automation proving ground because it gives frequent intraday
feedback and tests the order lifecycle we need for higher-timeframe systems.

## Tradovate Cost/Access Notes

Checked 2026-05-23:

- Tradovate support says API access requires a live Tradovate account with more
  than `$1,000`, the CME Information License Agreement, and an API Access
  add-on.
- Tradovate's non-professional market-data page lists Level I top-of-book data
  at `$4/month` per CME-group exchange, or `$12/month` for the CME Group bundle.
- Tradovate also documents an API-key flag that allows orders to be sent without
  a Tradovate market-data subscription when using other market-data
  subscriptions.

Sources:

- `https://tradovate.zendesk.com/hc/en-us/articles/4403105829523-How-Do-I-Get-Access-to-the-Tradovate-API`
- `https://tradovate.zendesk.com/hc/en-us/articles/115011506088-What-are-the-non-professional-market-data-rates`
- `https://tradovate.zendesk.com/hc/en-us/articles/4403100181651-Do-I-Need-a-Market-Data-Subscription-Through-Tradovate-to-Perform-Trades`

The exact API add-on dollar amount should be confirmed inside the Tradovate
application before funding the account. Public support pages confirm the add-on
requirement but do not display the live price in text.

## Cloud Shape

Use one small EC2 instance first:

- EC2: `t4g.small` or `t4g.medium`
- OS: Ubuntu 24.04
- Disk: 50-100 GB encrypted gp3
- Runtime: Docker Compose
- State: local flat files on EBS
- Secrets: start with environment/SSM later, never committed
- Monitoring: container restart policy plus health endpoint

The first deploy target now lives in:

- `live/deploy/engine.conf.example.json`
- `live/deploy/Dockerfile`
- `live/deploy/docker-compose.yml`
- `live/deploy/terraform/`

## Config Contract

The config file owns the deployable shape:

```json
{
  "strategy": {
    "strategy_id": "mnq_v2b_1_0_0_demo",
    "strategy_type": "v2b_scaleout",
    "instrument": "MNQ",
    "broker_instrument": "MNQ_ACTIVE_CONTRACT",
    "account_mode": "paper",
    "timeframes": "1m",
    "max_contracts": 1,
    "config": {
      "mode": "oco_then_reverse",
      "entry_qty": 1,
      "tp1_qty": 1,
      "tp2_qty": 0,
      "use_regime_filter": true,
      "require_regime_dates": true,
      "regime_dates": []
    }
  },
  "broker": {
    "provider": "paper",
    "mode": "paper",
    "allow_live_routing": false
  }
}
```

`broker-paper` and `broker-live` are intentionally not enabled by the bootstrap
runner yet. The next implementation step is a Tradovate broker adapter behind
the existing `OrderIntent` contract.

## First Done State

This phase is done when an EC2-hosted container can:

- initialize `mnq_v2b_1_0_0_demo` from `engine.conf`,
- expose `/healthz`,
- accept completed 1m bar jobs,
- produce v2b order intents in local paper mode,
- write orders/fills/positions/reports under persistent state,
- restart without duplicating state,
- and block any config that attempts live routing.
