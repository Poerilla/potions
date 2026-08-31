# Entry / signal parity — findings

## Why analytic & broker do not share trades near-perfectly

### 1. Next-bar death (ordering / live_after) — dominant on broker book
PaperBroker requires `bar.ts` **strictly after** `live_after_ts`.
- Analytic fills the **touch bar** at exact limit.
- Broker: touch bar submits limit → fill on **next** minute (+ slip).
- After fill, `on_bar_close` can arm `st_flip` same bar; market fills the following bar → **~1 minute hold**.

On the existing scale_run broker run:
- **69%** of campaigns exit with hold ≤ 1 minute (PnL **−$258k**)
- hold > 1 minute: **+$155k** on 70 trades

Survivors of the entry bar are net positive. Pessimistic / next-bar mechanics are not a small friction — they define the book.

### 2. Different signal→entry path (even before ST divergence)
| | Analytic | Broker |
|--|--|--|
| Fill bar | touch bar | touch+1 (strict live_after) |
| Fill price | exact structure | structure ± slip (~0.7 pts mean) |
| Same-bar manage after fill | no (manage ran before fill) | yes (on_bar_close after fill) |
| Stop-first vs targets | n/a at entry | once stops+targets live, stops first |

### 3. Position blocking feeds back into signal set
Longer analytic holds block later ST breaks; broker dies fast and would re-arm — but its **own** ST/structure path still produces fewer profitable entries. Entry-day overlap was only ~70 days.

### 4. ST implementation edge cases
Analytic: `compute_supertrend` on warm+day tape. Plugin: incremental EWM, 2-session warm. Same formula family; can diverge at session edges.

## Tests queued
1. **Analytic-as-signal + touch** — plugin executes analytic `trades.csv` arms only (`signal_source=external`).
2. **Analytic-as-signal + sweep_reclaim** — require SL touch, then reclaim through entry before submitting limit.

DSR: TRL-2026-00080 / 00081.

## Test results (2026-08-03)

| Mode | Trades | Net | PF | hold≤1 share | hold≤1 $ | hold>1 $ |
|------|-------:|----:|---:|-------------:|---------:|---------:|
| Internal signals + touch (baseline) | 228 | −$103k | 0.70 | 69% | −$258k | **+$155k** |
| Analytic signals + touch | 111 | −$217k | 0.17 | 73% | −$193k | −$24k |
| Analytic signals + sweep_reclaim | 286 | −$441k | 0.42 | 75% | −$719k | **+$278k** |

### Takeaways
1. **Feeding analytic signals does not fix the broker book** under touch entry — fewer fills (blown during next-bar delay) and still ~1-minute deaths.
2. **sweep_reclaim** gets more fills and better *survivor* PnL (+$278k on hold>1), but worsens total because most campaigns still die on the next bar via adverse `st_flip` / risk.
3. **Ordering / next-bar fill+ST manage is the binding constraint**, not “wrong signals.” Fix candidates: delay ST-flip N bars after entry, enter on reclaim with market and suppress same/next-bar ST flatten, or align analytic to next-bar fill semantics.

Artifacts:
- `../structure_program_st_broker_scale_run_ext/`
- `../structure_program_st_broker_scale_run_ext_reclaim/`
- signals: `analytic_filled_signals.csv`

## Structure-only resting (no ST signal) — 2026-08-03

Intent: rest a limit at the program structure key every day; ST no longer arms entry
(exits still `fav_be`). Fixed after an invalid marketable-churn run (TRL-2026-00082).

| Mode | Trades | Net | PF | hold≤1 share | hold≤1 $ | hold>1 $ |
|------|-------:|----:|---:|-------------:|---------:|---------:|
| Internal ST + touch | 228 | −$103k | 0.70 | 69% | −$258k | +$155k |
| **structure_only resting** | **493** | **−$2.13M** | **0.185** | **82%** | **−$2.55M** | +$421k |

**FAIL** (TRL-2026-00083). More entries without ST = more short-hold losses; survivor
bucket still green. Details: `../structure_program_st_broker_struct_v2/STRUCT_RESTING.md`.

### v2b target alignment
Structure keys vs same-day OR/v2b levels: **77.6% against** first-break side;
dir-aligned days put only ~7% of keys in the 0–2R path. Not the same levels as
v2b TP1/TP2. Hub: `../../structure_program_st/v2b_align/SUMMARY.md`.
