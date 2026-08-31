# CONFIG — V2B Clean-Break Pyramid Trail CFD Validation V1

STATUS: RESEARCH ONLY
CONFIG_HASH: `b0447e344dddd465`
PARENT: `v2b_clean_break_pyramid_trail_cfd_top3_v1` / `TRL-2026-00196`

## Frozen variants (exact)

- `trail06_m8_e2_out_be` — max 8, add every 2 outside bars, trail@0.6→BE
- `trail06_m4_e1_opp_be` — max 4, add every 1 opposing outside, trail@0.6→BE
- `trail06_m4_e2_out_be` — max 4, add every 2 outside bars, trail@0.6→BE

## Session / base rules (match parent)

- OR: 09:30–09:45 America/New_York on completed 5m bars.
- Buy stop: OR high + 2 CFD ticks (tick=0.1 → OR high + 0.2).
- Stop may fill on any post-OR 5m bar once armed (required_break_num=0).
- Clean-close: after fill, on the fill bar close, require close > OR high;
  low at/below OR low − 1 tick → ambiguous flatten; close ≤ OR high → failed_clean_close.
- Reference: OHLC mid (no bid/ask series).
- Same-bar: entry stop can fill intrabar; clean validation at that bar's close;
  protective pyramid exits active from subsequent bars.

## Outside / pyramid

- Outside bar: **low > OR high** (strict).
- Add size: 1 unit; base unit counts toward max.
- Add order: market, live_after_ts = bar close; no add while add pending/working.
- Soft exit: completed 5m close ≤ OR high → market flatten (priority over adds).
- EOD: 15:55 flatten.

## Trail / BE / 2R

- Trigger: bar high ≥ entry + 0.6×(2R − entry), where entry = **initial base fill**,
  2R = entry + 2×(OR high − OR low) from `_params` (range-based, not weighted avg).
- On trigger bar close: submit BE stop at entry + 2R limit for full qty
  (`live_after_ts` = bar ts; fills from subsequent bar path).
- Later adds: refresh trail_stop/target qty to current position; BE level stays at base entry.
- Soft exit / EOD / trail stop / target: PaperBroker same-bar stop-first realism.

## Data provenance

| Market | Path | Basis | Tick | Point $ | Fee/unit | Source hash (1st 2MB) |
|---|---|---|---:|---:|---:|---|
| NAS100 | `fx/nas100_1m.csv` | PROXY OHLC 1m→5m RTH resample | 0.1 | 1.00 | 1.50 | `7f9445ae4949a800` |
| US30 | `fx/us30_1m.csv` | PROXY OHLC 1m→5m RTH resample | 0.1 | 1.00 | 1.50 | `6776706ccb716689` |
| SPX500 | `fx/spx500_1m.csv` | PROXY OHLC 1m→5m RTH resample | 0.1 | 1.00 | 1.50 | `028cd71b08260d62` |

**DATA QUALITY: PROXY DATA — PORTABILITY EVIDENCE LIMITED**

- Provider: local `fx/*_1m.csv` OHLC (not verified broker bid/ask CFD quotes).
- Timezone: UTC source → America/New_York RTH filter 09:30–16:00.
- Bar construction: 1m→5m OHLC resample via `load_market_5m` (parquet cache).
- Spread model: **MODEL B fixed** — Engine default adverse slippage ticks (base=1);
  no historical bid/ask. Same model for NAS100/US30/SPX500.
- Holiday / early-close / weekend: bars absent when missing in source; no special calendar overlay.

## PARENT RULE AMBIGUITIES (resolved once for all markets)

1. Soft exit vs trail stop same bar → PaperBroker stop-first then other exits.
2. Trail uses base fill entry, not VWAP of adds.
3. Adds remain eligible after trail/BE armed (parent behavior).
4. S6 partial add: fractional lots unsupported → deterministic alternate skip.
5. S8 gap stress: PaperBroker gap-through + +4 adverse ticks on marketable fills.

## Chronological split

- Development = earlier 70% of sessions; Holdout = most recent 30%.
- Frozen before validation; holdout does not select variants.
