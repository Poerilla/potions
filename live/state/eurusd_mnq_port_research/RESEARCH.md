# EURUSD ports of untried MNQ research

**Status:** Complete (2026-07-18)  
**Verdict:** No new FX sleeve. All Wave A/B scouts failed the promotion gate. Wave C deferred.

## Method

- Scout driver: `live/eurusd_mnq_untried_scout.py` (+ `eurusd_mnq_untried_helpers.py`)
- Path/pandas sims (closed-equity DD), not Engine stress
- Economics: 1 standard lot, PV $100k, fee $1.50/unit, ~0.5 pip half-spread
- ORB session: NY 09:30–09:45; window 2015-01-01 → 2026-03-31
- Gate: `(net > 0 and Net/closed-DD ≥ 1.0)` or `net ≥ $23.5k with positive Net/DD`

Full table: [`../eurusd_mnq_untried_scout/SUMMARY.md`](../eurusd_mnq_untried_scout/SUMMARY.md)

## Wave A (NY ORB) — all fail

| Idea | Net | Net/DD |
|---|---:|---:|
| Adaptive 50/150 v2b-only | −$11.2k | −0.92 |
| Adaptive v2b + v2d fade | −$38.5k | −0.98 |
| Clean-break | −$31.7k | −0.99 |
| v1b pullback | −$49.2k | −0.99 |
| ORB open-limit | −$49.1k | −0.99 |
| Breakout-close limit | −$107.0k | −0.99 |
| Swept-liquidity ORB | −$26.1k | −1.00 |

## Wave B (London / calendar) — all fail

| Idea | Net | Net/DD |
|---|---:|---:|
| ATR fade-touch (NY midnight) | −$1.5k | −0.48 |
| Prior-month sweep daily | −$7.1k | −0.26 |
| Fib-62 London pullback | −$9.5k | −0.82 |
| C3-hit → OR fade | −$15.5k | −0.91 |
| Daily C3 breakout | −$68.4k | −0.36 |
| Midnight flip NY / London | −$137k / −$207k | −0.89 / −0.97 |
| Monthly C3 breakout | −$291k | −0.81 |

## Broker-like

**None.** Zero survivors → no Engine/PaperBroker promotion runs.

## Wave C (deferred — parent never cleared)

- v2b_child / open-limit child
- v2b_m monthly-break bias
- Monthly ORB overlap ST retest / stop-limit cycle
- `adaptive_experiment` 60% retrace / strict clean-break forks

## Already tried on FX (skipped by design)

Yearly ORB, Monthly ORB restricted/boundary, ATR DCA, Hourly ST+PMC (promoted baseline),
ungated v2b OCO, prior-opposed / PMC / YORB / monthly-swing gates, London sweep reversal,
OR fade, WO gap, weekly-mid, 15m ST DCA/fade, baseline+DCA.

## Keepers unchanged

| Sleeve | Location |
|---|---|
| Yearly ORB scaleout3 (~$166k / 8.3) | `../eurusd_overnight_sweep/` |
| Hourly ST+PMC MA-bull (~$23.5k / 1.49) | `../eurusd_forex_intraday_baseline/` |
