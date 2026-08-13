# Plan: HP condition overlays on live/demo

Source: `live/state/intraday_condition_overlay` (broker-like campaign tapes + chronological 60/40 OOS).
Features are **entry-asof** (pre-fill). No mid-trade add-on studied.

## Verdict

**Worth pursuing as size overlays on already-good books.** Hard filters are secondary (risk throttle / sit-out), not a blanket replace-the-book gate.

Ignore EURUSD v2b “filter wins” — OOS baseline is deeply negative; filtering only loses less. Prefer size-up on books with **positive OOS baseline net**.

ATR quartile lifts look real but need a **causal rolling percentile** before live — deferred.

## Tier A — size-up candidates (live-ready, +OOS book)

| Priority | Book | Condition | HP≈ | Mult | OOS Δnet | Notes |
|---|---|---|---:|---:|---:|---|
| A1 | USDJPY Monday OR | week_opposed | 70% | **1.25×** first | +27k | 1.5× also works (+53k) but nearly blanket boost — start 1.25 |
| A1 | USDJPY Monday OR | week_of_month=2 | 21% | **1.5×** | +22k | Sparse calendar; stress≈flat |
| A1 | USDJPY Monday OR | Thursday | 14% | **1.25–1.5×** | +6–13k | Cross-book DOW hit |
| A2 | USDJPY Asia-range | hour_ny=4 | 14% | **1.25–1.5×** | +12–23k | Strong single + cross |
| A2 | USDJPY Asia-range | ma_opposed | 12% | **1.25–1.5×** | +10–21k | Cross-book MA |
| A2 | USDJPY Asia-range | rsi_gt70 | 6% | **1.25–1.5×** | +7–14k | Thin but clean |
| A3 | EURUSD ST+PMC | Thursday / rsi_against | 21–23% | **1.25×** | +3–8k | Prefer 1.25; filter also strong |
| A3 | US30 Monday OR | Fri / hour 10–11 / rsi_55_70 | 9–29% | **1.25–1.5×** | +2–5k | Modest $ but N/S up |
| A3 | US30 London prior | hour=3 / ma_opposed | 32–33% | **1.25×** | +1.7–3.5k | Small book — cap risk |
| A3 | NAS100/US30 ST+PMC | Fri / Thu / rsi_against / wom=2 | 17–34% | **1.25×** | +0.5–1.8k | Cross Fri/Thu pattern |

**Cross-book size rule of thumb:** start **1.25×** for signals hitting ≥3 profitable books (Fri, Thu, week_opposed, rsi_against, wom=2/4). Use **1.5×** only on single-book A1/A2 cells after shadow.

## Tier B — filter / sit-out (optional)

Only where leftover book stays profitable OOS and N/S rises:

| Book | Filter | HP keep | OOS effect |
|---|---|---:|---|
| EURUSD ST+PMC | Thursday only *or* rsi_against | ~21–23% | Net↑ and N/S 0.33→~2.5–3.9 |
| USDJPY Monday OR | week_opposed only | ~70% | Mild net↑, N/S 4.7→7.3 (risk throttle) |
| US30 Monday OR | week_opposed | ~75% | Small net↑, N/S↑ |
| EURUSD Monday OR | hour=14 / Thu / ma_opposed / rsi_against | 3–19% | Salvages negative OOS period — treat as **sit-out research**, not size |

Do **not** hard-filter EURUSD/NAS100 v2b ungated into “HP only” and call it a promote — baseline is still broken.

## Causality / timing

| Feature | At fill? | Live action |
|---|---|---|
| DOW / week-of-month / NY hour | Yes | OK for size/filter |
| 5m MA align, hourly RSI/OBV, prior day/week/month half | Yes (asof entry) | OK |
| ATR quartile (static book cut) | Research-only | Build rolling ATR% before use |
| Post-fill regime change | No | Ignore for intraday; multi-day Monday OR add-on needs a separate study |

## Staged live/demo rollout

**Authorized primary (strict nulls, 2026-08-12):** EURUSD ST+PMC **Thursday @1.25×**
and US30 Monday OR **hour 11 @1.25×** only — see
[`../intraday_hp_sizeup_nulls/ROLLOUT.md`](../intraday_hp_sizeup_nulls/ROLLOUT.md).
1.5× = borderline paper; 2× = risk-budget only (not validated).

1. **Shadow (now)** on those two paper demos: log `hp_flag` / `would_size_mult`
   via `python -m live.hp_size_shadow --once` → `state/hp_shadow.csv`. **No size change**
   (qty=1 books cannot apply 1.25× without base-lot rescale).
2. **Paper size-up** at **1.25×** only after lot geometry supports it (e.g. base 4→5).
   Cap: at most one HP boost per account / no stacking multipliers.
3. Plugin hook (later): config list `hp_size_rules: [{feature, value, mult}]` evaluated in
   order-intent **before** submit (same asof as research).
4. Keep existing `skip_entry_months` / shadow WR-PF gates — HP is an overlay.
5. After ~50–100 live HP campaigns, re-run overlay OOS-style; promote 1.5× only if
   `p_master≤0.05` (or keep explicitly labelled borderline paper) and stress ≤~1.35×.
6. Optional later: EURUSD ST+PMC Thursday **filter** sleeve as a parallel paper book.

Broader Tier A cells (USDJPY week_opposed / hour=4 / etc.) remain research candidates
until they clear the same strict matched-null classifier at the intended multiplier.

## Out of scope for now

- Stacking multiple HP rules (max mult, not product).
- Mid-trade scale-in on multi-day Monday OR.
- ATR size-up until causal percentile exists.
- Promoting size on negative-baseline v2b books.
