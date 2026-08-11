# Shadow WR/PF + month filters — how they work

## Short answer

**Yes — the rolling WR/PF gate is a shadow book of unfiltered campaign outcomes**, not “only trades we took.”

Taken-only windows freeze after the first PF dip (you sit out forever). Research and the live contract both require the window to advance on **what the strategy would have done every session**, including days the live book paused.

Shadow PnLs are **not broker tickets**. They are campaign nets from sims on collected candles (research tape, or live EOD candle-sim) that only inform whether the next session may arm.

## Two filters (both required for the promote cell)

| Filter | What | Why |
|--------|------|-----|
| **Month blackout** | `skip_entry_months=[1]` (January, NY calendar) | Consistently negative across years on sizing tapes (`neg_frac_years` + mean year net &lt; 0) |
| **Shadow roll50** | Prior 50 unfiltered campaigns: sit out if WR &lt; 40% **or** PF &lt; 1 | Cuts the worst regimes without freezing the gate |

## Research path (broker-like promote evidence)

Driver: `live/fx_v2b_asia_range_london_usdjpy_filters.py`  
Hub: `live/state/fx_v2b_asia_range_london_usdjpy_filters/`

1. **Month audit** on unfiltered sizing tapes → lock **January**.
2. **Shadow gate** walks the **full unfiltered** campaign tape chronologically. For campaign *i*, look at prior 50 nets; if WR &lt; 40% or PF &lt; 1, mark that session to sit out.
3. **Broker-like replay** (Engine + PaperBroker) only on allowed sessions → filtered metrics.

Research does **not** place live shadow orders during the filtered run; it uses the prior full sim as the shadow book, then filters the day list. That is the same information a live candle-sim would produce, offline.

## Live path (demos)

Module: `live/asia_range_shadow.py`  
Plugin knobs on `v2b_scaleout`: `skip_entry_months`, `shadow_roll_window`, `shadow_min_wr`, `shadow_min_pf`, `shadow_campaigns_path` / seed.

1. Seed `shadow_campaigns.json` from the last 50 unfiltered `S_3_1_3` campaigns (sizing hub).
2. Each London day: build Asia H/L from collected 1m quotes (19:00–03:00), inject `session_or_ranges`, arm at 03:00 if filters pass, flatten 11:59.
3. After EOD: append today’s **unfiltered** campaign net into the shadow book so tomorrow’s gate keeps moving.
   - **Traded days:** append live campaign net from `unit_trades` (when present).
   - **Sit-out days:** append a candle-sim net (same unfiltered rules, no live broker order)
     via `candle_sim_unfiltered_campaign_net` in `usdjpy_asia_range_london_common.py`
     so the roll window cannot freeze.

Gate evaluation itself is live and causal: `_session_tradeable` reads prior-N from the shadow JSON/state before arming.

## Why this belongs in rankings / decision making

- Unfiltered USDJPY Asia-range leaders sat ~N/S **2.1–2.2**. Same book with Jan + roll50 → **N/S 7.23** (~3×) with stress cut from ~−$72k (`S_3_1_3` sizing) to **−$25k**.
- Month blackouts match the Monday OR Aug/Sep pattern; rolling WR/PF is the generalisation for regime sit-outs on campaign sleeves.
- **Do not** score the rolling gate on taken-only trades — that is a known failure mode (`asia_range_shadow` docstring).

Teachers: `potions-quick-backtest` (Decision filters), `potions-tracker-docs` (FILTERS.md pattern), `potions-repo-router` (Month / rolling WR-PF row).

## Promoted cell

| Book | Filters | Net≈USD | Stress | **N/S** | WR | PF |
|---|---|---:|---:|---:|---:|---:|
| **USDJPY `S_3_1_3`** | Jan skip + roll50 WR40/PF1 | +$178k | −$25k | **7.23** | 48.6% | 1.294 |

Unfiltered `S_3_3_3` on the same hub: N/S **2.14**. Filtered `S_3_3_3` / `S_0_5_0` also ~6.7–7.1; **`S_3_1_3`** wins N/S and is the live book.

Live: `demo-usdjpy-asia-range-{paper,oanda}` → `live/demo/usdjpy_asia_range_london_{paper,oanda}/`.

## Funded-sleeve gates (not automatic)

Research promote ≠ funded sleeve. Before calling this a funded sleeve, keep
[`VALIDATION_GATES.md`](VALIDATION_GATES.md) green (or consciously waive):

1. **Frozen-rule OOS** — lock `S_3_1_3` + Jan + roll50 WR40/PF1; test later years without retuning.
2. **Walk-forward stability** — yearly / anchor tables; not one narrow USDJPY regime.
3. **Filter attribution** — Jan / WR / PF / combined contributions on the shadow tape.
4. **Path-aware risk** — broker fills, OCO, slippage, simultaneous exposure, worst campaign, margin (hub logs + weekly post-process; driver scrapes fills/orders into `validation_path_aware.json`).
5. **Live-parity audit** — paper `campaign_parity.csv` vs research `validation_decision_tape.csv`.

**50-campaign warmup:** the roll gate cannot fire until 50 prior unfiltered campaigns exist.
Demos seed last-50 from the sizing hub; cold research replays still pass through the first 50 on WR/PF (Jan still applies).
Proof windows can shrink when the shadow book is already seeded / market history is short.

**Filter nulls:** [`FILTER_NULLS.md`](FILTER_NULLS.md) — **RETAIN AS RISK THROTTLE** (not alpha). Does not unlock funded capital alone.

**Three-book forward discriminator:** [`THREE_BOOK_FORWARD.md`](THREE_BOOK_FORWARD.md) —
A unfiltered / B January-only / C Jan+roll50. Locked hierarchy
`C_PRIMARY_CAPITAL_EFFICIENT_B_ALPHA_CONTROL`: **C** = primary capital-efficient
demo (broker N/S 7.23; scalable within stress budget); **B** = alpha/return
control (frozen OOS N/S winner — January is the return lever); **A** = unfiltered
shadow control. Practice demos stay on C; do not treat C's full-sample N/S as
funded-rule proof. Scale C with lot/margin/OCO validation, not pure linearity.

**Still open before funded:** live parity row-for-row compare after first London campaigns
fire (`campaign_parity.csv` vs `validation_decision_tape.csv`). Sit-out candle-sim append
is wired on demos. Margin ops: weekly `oanda-practice-sync` (fields now on snapshot).

Drivers:
- `python -m live.fx_v2b_asia_range_london_usdjpy_validation --email`
- `python -m live.fx_v2b_asia_range_london_usdjpy_filter_nulls --email`
- `python -m live.fx_v2b_asia_range_london_usdjpy_three_book_forward --email` (optional `--broker-jan`)
