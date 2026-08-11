# USDJPY Asia-range London — frozen three-book forward comparison

Rules locked (no retune): book **`S_3_1_3`**, January skip, roll50 WR≥40% / PF≥1.0,
shadow = **unfiltered** campaign nets. OOS cut: years **> 2021**.

| Book | Variant |
|---|---|
| **A** | Unfiltered `S_3_1_3` |
| **B** | January-only `S_3_1_3` |
| **C** | January + roll50 WR40/PF1 `S_3_1_3` (promote cell) |

## Verdict

**B WINS FROZEN FORWARD (net/N/S); C remains risk throttle** — January-only beats combined on OOS net and OOS N/S; roll gate still cuts full-sample stress. Aligns with FILTER_NULLS risk-throttle stance; do **not** treat C's full-sample N/S beauty as funded-rule proof.

- Full-sample shadow N/S winner: **C** (6.07).
- Frozen OOS shadow N/S winner: **B** (6.56, OOS net $+169066).
- C vs B OOS: Δnet $-67376 | ΔN/S -2.32 | full-sample stress |C| vs |B|: 24017 vs 53686.

## 1. Shadow tape scorecard (primary discriminator)

Source: sizing hub unfiltered `unit_trades` for `S_3_1_3`. Stress / max DD are
closed-campaign equity drawdowns on the taken tape (reachable-stress proxy).

| Book | Taken | Skip | Net≈USD | Stress | N/S | Max DD | Worst | PF | WR | OOS n | OOS net | OOS N/S |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| **A** S_3_1_3 | 1673 | 0 | $153741 | $-68391 | 2.25 | $-68391 | $-12473 | 1.143 | 49.2% | 793 | $150267 | 5.35 |
| **B** S_3_1_3 | 1508 | 165 | $182627 | $-53686 | 3.40 | $-53686 | $-12473 | 1.195 | 49.7% | 721 | $169066 | 6.56 |
| **C** (promote) | 879 | 794 | $145792 | $-24017 | 6.07 | $-24017 | $-12473 | 1.229 | 49.6% | 528 | $101690 | 4.23 |

### Read

- **A → B**: January skip is the only positive-Δ net lever on the full tape
  (B net $+182627 vs A $+153741).
- **B → C**: roll gate sacrifices OOS net ($+169066 → $+101690) and OOS N/S (6.56 → 4.23)
  while cutting full-sample stress ($-53686 → $-24017).
- Full-sample N/S ranks **C > B > A**; frozen OOS N/S ranks **B(6.56) > A(5.35) > C(4.23)**.

## 2. Broker-like reference (PaperBroker)

| Book | Variant | Present | Trades | Net≈USD | Stress | N/S | WR | PF |
|---|---|---|---:|---:|---:|---:|---:|---:|
| **A** | unfiltered | yes | 1673 | $153741 | $-71846 | 2.14 | 47.5% | 1.142 |
| **B** | january_only | yes | 1508 | $182627 | $-54589 | 3.35 | 48.1% | 1.194 |
| **C** | combined | yes | 861 | $178142 | $-24627 | 7.23 | 48.6% | 1.294 |

Broker N/S ranks: **C(7.23) > B(3.35) > A(2.14)**.

## 3. Yearly taken net (shadow)

| Year | A taken/net | B taken/net | C taken/net | OOS? |
|---:|---|---|---|---|
| 2015 | 216 / $+49069 | 193 / $+43668 | 186 / $+39341 |  |
| 2016 | 36 / $+7302 | 31 / $+4443 | 31 / $+4443 |  |
| 2017 | 114 / $-13759 | 91 / $+264 | 8 / $+5492 |  |
| 2018 | 157 / $-30368 | 137 / $-30354 | 24 / $-963 |  |
| 2019 | 77 / $-11716 | 73 / $-11293 | 21 / $-3689 |  |
| 2020 | 47 / $+17211 | 29 / $+21099 | 5 / $+9360 |  |
| 2021 | 233 / $-14265 | 233 / $-14265 | 76 / $-9882 |  |
| 2022 | 256 / $+79389 | 231 / $+86768 | 175 / $+63616 | yes |
| 2023 | 167 / $+18342 | 167 / $+18342 | 117 / $-3158 | yes |
| 2024 | 148 / $+43709 | 145 / $+35284 | 137 / $+30651 | yes |
| 2025 | 156 / $+21426 | 132 / $+36929 | 82 / $+22656 | yes |
| 2026 | 66 / $-12598 | 46 / $-8258 | 17 / $-12074 | yes |

## 4. Funded-sleeve implication

- Research/practice promote cell remains **C** for live demos (already wired).
- Filter nulls: **RETAIN AS RISK THROTTLE** (`FILTER_NULLS.md`).
- This forward cut asks whether roll50 is *necessary* beyond January for a
  defensible funded rule. Verdict code: **`B_WINS_FORWARD_C_RISK_THROTTLE`**.
- Funded sleeve stays **NO** until live parity + (if keeping C) a clear story that
  sacrificed OOS net buys robust path risk investors actually need.

Driver: `python -m live.fx_v2b_asia_range_london_usdjpy_three_book_forward --email`
Optional broker B: add `--broker-jan`.

Hub: `/home/tester/hsm/potions/live/state/fx_v2b_asia_range_london_usdjpy_filters`

