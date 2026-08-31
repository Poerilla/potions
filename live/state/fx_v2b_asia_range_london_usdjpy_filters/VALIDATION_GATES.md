# USDJPY Asia-range London — funded-sleeve validation gates

**Stance:** research **PROMOTE** / paper+OANDA practice demos are live.
**Funded sleeve:** **NOT YET** — these gates must stay green (or consciously waived) first.

## Frozen rules (locked — no retune)

| Knob | Value |
|---|---|
| Book | `S_3_1_3` (3/1/3) |
| Month blackout | January (`skip_entry_months=[1]`) |
| Shadow window | 50 campaigns |
| Min WR | 40% |
| Min PF | 1.00 |
| Shadow book | **unfiltered** campaign nets |

### 50-campaign warmup

The rolling WR/PF gate cannot fire until **50 prior unfiltered campaigns** exist.
Live demos **seed** the last 50 from the sizing hub so paper/OANDA do not sit in a cold warmup,
but any fresh research replay from `2015-01-02` still has a true first-50 pass-through on the roll gate
(January blackout still applies). Proof windows can be shortened only when the shadow book is pre-seeded.

## 1. Filter attribution (shadow campaign tape)

Source: unfiltered sizing `unit_trades` for `S_3_1_3` (campaign nets, ≈USD at JPY/110).
Δ = taken net − unfiltered net (= −skipped net). Positive Δ means the filter avoided net losses.

| Variant | Taken N | Taken net≈USD | Skipped N | Skipped net≈USD | Δ vs unfiltered |
|---|---:|---:|---:|---:|---:|
| Unfiltered | 1673 | $153741 | 0 | $0 | $+0 |
| January only | 1508 | $182627 | 165 | $-28886 | $+28886 |
| Rolling WR only | 1481 | $144665 | 192 | $9076 | $-9076 |
| Rolling PF only | 992 | $117945 | 681 | $35796 | $-35796 |
| Rolling WR+PF | 990 | $116387 | 683 | $37354 | $-37354 |
| **Combined (promote)** | 879 | $145792 | 794 | $7949 | $-7949 |

**Read:**
- January exclusion contribution: **Δ ≈ $+28886** (skipped 165 Jan campaigns, skipped net ≈ $-28886).
- Rolling WR gate alone: **Δ ≈ $-9076** (mostly sits out winners on this tape — not a solo lever).
- Rolling PF gate alone: **Δ ≈ $-35796** on raw campaign net; it is the **dominant sit-out** (681 skips).
- Combined: **Δ ≈ $-7949** on shadow net; broker-like filtered hub remains the ranking proof (N/S **7.23**).
- Result does **not** depend only on January: roll gate still skips **629** sessions in the combined book (reasons on decision tape).

Combined skip reasons: `{'pf': 462, 'month': 165, 'both': 165, 'wr': 2}`

## 2. Walk-forward / yearly stability (frozen combined)

| Year | Campaigns | Taken | Skipped | Taken net≈USD | Abs-net share |
|---:|---:|---:|---:|---:|---:|
| 2015 | 216 | 186 | 30 | $+39341 | 19.2% |
| 2016 | 36 | 31 | 5 | $+4443 | 2.2% |
| 2017 | 114 | 8 | 106 | $+5492 | 2.7% |
| 2018 | 157 | 24 | 133 | $-963 | 0.5% |
| 2019 | 77 | 21 | 56 | $-3689 | 1.8% |
| 2020 | 47 | 5 | 42 | $+9360 | 4.6% |
| 2021 | 233 | 76 | 157 | $-9882 | 4.8% |
| 2022 | 256 | 175 | 81 | $+63616 | 31.0% |
| 2023 | 167 | 117 | 50 | $-3158 | 1.5% |
| 2024 | 148 | 137 | 11 | $+30651 | 14.9% |
| 2025 | 156 | 82 | 74 | $+22656 | 11.0% |
| 2026 | 66 | 17 | 49 | $-12074 | 5.9% |

Positive years: **7** / negative-or-flat: **5**. Largest abs-net share: **31%** in **2022**.
Stability heuristic (share &lt; 50% and ≥5 green years): **PASS**.

### Causal anchors (prior-50 WR/PF at each Jan 1)

| Anchor | Prior N | Shadow WR | Shadow PF | Blocks? | That-year taken net≈USD |
|---|---:|---:|---:|---|---:|
| 2016-01-01 | 216 | 54.0% | 1.95 | no | $+4443 |
| 2017-01-01 | 252 | 60.0% | 1.48 | no | $+5492 |
| 2018-01-01 | 366 | 48.0% | 0.94 | yes | $-963 |
| 2019-01-01 | 523 | 42.0% | 1.19 | no | $-3689 |
| 2020-01-01 | 600 | 38.0% | 0.41 | yes | $+9360 |
| 2021-01-01 | 647 | 44.0% | 1.92 | no | $-9882 |
| 2022-01-01 | 880 | 40.0% | 0.84 | yes | $+63616 |
| 2023-01-01 | 1136 | 54.0% | 1.46 | no | $-3158 |
| 2024-01-01 | 1303 | 50.0% | 1.63 | no | $+30651 |
| 2025-01-01 | 1451 | 54.0% | 1.33 | no | $+22656 |
| 2026-01-01 | 1607 | 64.0% | 1.56 | no | $-12074 |

## 3. Frozen-rule out-of-sample (no threshold retune)

Rules locked as above. Holdout = calendar years **after** the cut (still causal roll history).
Note: January was originally audited on the full sizing tape — this is **frozen-rule** OOS, not a claim that month selection was blind.

| Fit through | Fit taken net≈USD | OOS taken N | OOS skip N | OOS taken net≈USD | OOS WR | OOS worst≈USD |
|---:|---:|---:|---:|---:|---:|---:|
| 2021 | $+44102 | 528 | 265 | $+101690 | 50.0% | $-12473 |
| 2022 | $+107718 | 353 | 184 | $+38075 | 48.4% | $-9565 |
| 2023 | $+104559 | 236 | 134 | $+41233 | 50.4% | $-9565 |

OOS after 2021 heuristic (net&gt;0 and N≥100): **PASS**.

## 4. Path-aware risk (promoted filtered broker hub)

Artifacts under `/home/tester/hsm/potions/live/state/fx_v2b_asia_range_london_usdjpy_filters/states/usdjpy_v2b_asia_range_london_S_3_1_3_flt`:

| Check | Value |
|---|---|
| Broker net≈USD | $+178142 |
| Stress DD≈USD | $-24627 |
| N/S | 7.23 |
| max_open_units (simultaneous) | 7 |
| max_fill_qty | 7.0 |
| Filtered worst campaign≈USD | $-12473 |
| Causality violation rows | 0 |
| fill rows / order rows | 1924 / 5640 |
| OCO cancelled / filled orders | 3717 / 1923 |
| fills adverse vs mid | 1555 / 1924 (mean abs diff 0.02) |
| fills/orders/unit_trades present | True / True / True |

Fill reasons: `{'entry': 861, 'eod_close': 727, 'tp1': 163, 'wide_stop': 107, 'tp2': 39, 'runner_stop': 27}`.
Cancelled by bracket role: `{'entry': 1143, 'tp2': 985, 'wide_stop': 754, 'tp1': 698, 'runner_stop': 137}`.

**2026-08-24 causality review:** the filtered `S_3_1_3` state has **3,772**
feature snapshots, **0** causality violations, and **0** entry fills at/before
order activation. Earliest entry fill is **1m** after the 03:00 London arm
decision. Review:
[`../usdjpy_causality_review_2026_08/CAUSALITY_REVIEW.md`](../usdjpy_causality_review_2026_08/CAUSALITY_REVIEW.md).

These counts are scraped from the filtered PaperBroker replay logs for weekly post-process;
they are not retune knobs. Margin under OANDA practice stays a demo ops / account-snapshot item.

### OANDA practice margin ops

| Field | Value |
|---|---|
| Dedicated account | `101-002-39860312-004` |
| Active config | `live/demo/oanda_account_configs/usdjpy_asia_range_004.json` |
| Target OANDA alias | `USDJPY Asia Range S313` |
| Prior shared-account snapshot | `2026-08-11T18:14:57Z` |
| Prior USDJPY open qty | 0.0 |

Refresh via `python -m potions.live.cli oanda-practice-sync` (weekly) after the
dedicated account is running. As of the 2026-08-24 rotation, account `-004`
replaces the retired NAS100 ST+PMC 2R->10R dedicated sleeve.

## 5. Live-parity audit (paper)

Paper/OANDA demos append `campaign_parity.csv` rows:
`session_date | shadow_50_wr | shadow_50_pf | skip/take | reason | realized_campaign_net | next_shadow_n`.
Compare row-for-row with research decision tape `validation_decision_tape.csv` (same columns).
Demos **seed** shadow last-50 so the roll gate is warm from day one; row compare starts once
London sessions fire (Asia OR collect → 03:00 inject).

Parity status: **pending_first_campaigns**

## 6. Filter nulls (risk-throttle evidence)

Separate study: [`FILTER_NULLS.md`](FILTER_NULLS.md) / `python -m live.fx_v2b_asia_range_london_usdjpy_filter_nulls --email`.
Overall: **RETAIN FILTER AS RISK THROTTLE** (not alpha) — matched-exposure / selection-aware fail;
circular-shift timing still supports the live gate; January #1/12 among month placebos.
Does **not** unlock funded sleeve by itself; keeps the promote book as an operational throttle.

## Open actions (funded sleeve still held)

| Item | Status |
|---|---|
| Frozen OOS / walk-forward / attribution offline proof | **done** (this hub) |
| Path-aware scrape of promoted fills/orders | **done** (regenerate via driver) |
| Filter nulls (matched-exposure / shift / selection-aware) | **done** — retain as risk throttle |
| OANDA practice margin fields on snapshot + asia demo in DEMO_FOCUS | **done** (weekly sync) |
| Live `campaign_parity.csv` row-for-row vs research tape | **pending_first_campaigns** |
| Sit-out candle-sim append on live skip days | **done** (demo common; unfiltered Engine on stored 1m) |

## Gate scorecard

| Gate | Status |
|---|---|
| Frozen-rule OOS (post-2021) | **PASS** |
| Walk-forward stability | **PASS** |
| Filter attribution (Jan not sole; roll sits out) | **PASS** |
| Path-aware risk logs present | **PASS** |
| Filter nulls stance | **RETAIN AS RISK THROTTLE** (see FILTER_NULLS.md) |
| Live-parity CSV wiring | **PASS** (compare: pending_first_campaigns) |
| Margin ops snapshot | **ok** |
| **Funded sleeve** | **NO — hold** |

Driver: `python -m live.fx_v2b_asia_range_london_usdjpy_validation --email`
