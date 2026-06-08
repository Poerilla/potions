# Adaptive 50/150 stitched — **scale-out** (2 MNQ)

This note describes a research variant of **`mnq_orb_results_adaptive_50_150.csv`**: same **daily regime routing** as `v2d/build_adaptive_trades.py` (prior-session-day **MA50 vs MA150** on MNQ daily closes selects **v2b** rows vs **v2d** rows), but each leg is **re-simulated on 1-minute MNQ** with **two contracts**, **partial at tier‑1 target**, and a **runner** to an extended target.

Executable driver: **`run_adaptive_50_150_scaleout.py`** (same folder as this file).

---

## Current research leader — v2b-only adaptive scaleout

As of the latest MNQ review, the cleanest winner is **not** the full v2b/v2d scaleout and not `v2b_child`; it is the **v2b-only split** of this scaleout book:

- Compute the same causal daily regime: prior-day **MA50 > MA150**.
- If true, trade the **v2b breakout** scaleout rules below.
- If false, **skip the day** instead of trading v2d.
- Use **2 MNQ**: one contract exits at TP1, the runner exits at TP2 or the runner stop.
- No child scale-ins.

Latest MNQ strict re-sim snapshot:

| Candidate | Legs | Net | Max DD | Win rate | PF |
|---|---:|---:|---:|---:|---:|
| **v2b-only adaptive scaleout** | **1,430** | **$35,847.00** | **-$5,190.00** | **55.03%** | **1.19** |
| Full adaptive scaleout, v2b + v2d | 1,831 | $30,218.50 | -$7,498.00 | 53.69% | 1.12 |
| Adaptive v2b_child/v2d 3max | 1,920 | $22,020.00 | -$5,411.50 | 49.69% | 1.14 |

The monthly-bias study found a slightly higher but more complex variant: keep v2b unchanged and allow only monthly-aligned v2d rows (**$35,903.00**, same **-$5,190.00** DD). Because that adds another regime dependency for only **$56** of extra MNQ net in this sample, the simpler **v2b-only adaptive scaleout** is the current lead candidate for execution testing.

### 2026-05 ordering audit

The later full-DBN scanner run (`benchmark_v2b_scaleout_candidates.py`) reproduced a much larger **$83,245 / -$3,130 MTM** result, but the order audit shows why it should not be treated as live/Pine parity. That script scans **Long first for the whole day**; if Long never fills, it can still accept a Short that may have happened earlier. This is useful as research, but it is not how the current Pine/TradingView OCO harness routes orders.

Use `paper_replay_v2b_scaleout_ordering.py` for execution-ordering checks:

| Scenario | Days | Legs | Net | Closed DD | MTM DD | Win | PF | Read |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| Long-priority scanner | 961 | 1,302 | $83,245 | -$2,730 | -$3,130 | 59.7% | 1.60 | Reproduces the headline, but not broker OCO |
| Broker-like OCO + reverse | 961 | 1,441 | $35,210 | -$5,190 | -$5,482 | 54.8% | 1.19 | Closest to current Pine/TradingView harness |
| Strict Long-then-Short | 737 | 1,078 | $19,600 | -$6,330 | -$6,672 | 53.3% | 1.15 | Literal executable "Long first; Short only after filled Long exits" |

Practical read: for live automation, compare paper fills to the **broker-like OCO** row, not to the $83k scanner row. The older stitched-CSV snapshot was directionally close to the broker-like OCO result.

Longer NQ confirmation: `potions/nq/v2d/run_adaptive_50_150_v2b_scaleout.py` shows the same structure stays positive over 2010-2026 NQ: **4,739 legs**, **$414,773.00 net**, **-$100,010.00 DD**, **51.89%** win rate, **1.13 PF**.

Reference reports:

- MNQ monthly/regime re-sim: `case_studies/monthly_orb/ADAPTIVE_SCALEOUT_MONTHLY_BIAS_RESIM.md`
- NQ long-sample confirmation: `../../nq/v2d/NQ_ADAPTIVE_50_150_V2B_SCALEOUT.md`

---

## Regime routing (unchanged vs stitched CSV)

- Source of truth for **which calendar dates** use **v2b** vs **v2d** legs is still **`build_adaptive_trades.py`**, which stitches rows from `mnq_orb_results_stops.csv` (v2b) and `mnq_orb_results_v2d.csv` (v2d).
- **Causal rule:** `regime_v2b = (MA50 > MA150).shift(1)` on the MNQ daily close series (first day defaults True where NaN-filled).

---

## Scale-out economics (both regimes)

| Item | Value |
|------|--------|
| Contracts at tier‑1 fill | **2 MNQ** |
| Fee | **\$1.50** round-trip **per contract** closed |
| Point value | **\$2** per index point **per contract** |
| Tick | **0.25** |

**Session clock (New York):** RTH **[09:30, 16:00)** on 1m bars; opening-range end **09:45**; no new intraday exits modeled from bar time **≥ 15:59**; remainder flattened at last RTH **close** before **16:00** (same convention as `case_studies/v2b_m/v2b_m_so/`).

**Multi-leg days:** Up to **two** legs per session day (OCO bracket path). Leg **2** fill scanning begins strictly **after** leg **1** exit bar (mirrors chart tooling in `build_adaptive_year_samples.py`).

---

## Tier‑1 fill discovery (1 m, **no extra slippage** beyond stop price)

### v2b (breakout)

- **Long:** first bar **after** OR anchor whose **high ≥ RH + tick**; fill **RH + tick**; initial stop **RL**; **TP1 = RH + Range**; **TP2 = RH + 2·Range**; runner stop after TP1 = **RH + tick** (breakeven vs fill).
- **Short:** first bar after anchor whose **low ≤ RL − tick**; fill **RL − tick**; initial stop **RH**; **TP1 = RL − Range**; **TP2 = RL − 2·Range**; runner SL = **RL − tick**.

### v2d (fade)

Matches the fade geometry used for targets/stops in `case_studies/v2d/build_adaptive_year_samples.py` when labeling charts:

- **Long fade:** require **short breakout** (**low ≤ RL − tick**) then buy stop fill **RL + tick**; initial stop **RL − Range**; **TP1 = RH**; **TP2 = RH + Range**; runner SL = **RL + tick** (breakeven vs fill).
- **Short fade:** require **long breakout** (**high ≥ RH + tick**) then sell stop fill **RH − tick**; initial stop **RH + Range**; **TP1 = RL**; **TP2 = RL − Range**; runner SL = **RH − tick**.

---

## Pessimistic bar ordering

On each **1 m** bar:

- **Before TP1:** wide initial stop **before** TP1 if both trade through.
- **On TP1 bar:** assume **runner stop** **before** TP2 if both levels trade on that minute.
- **Runner phase:** runner SL **before** TP2 when both touch.

*(Shorts use mirrored inequalities: stop with **high**, targets with **low**.)*

---

## Outputs / reproducibility

```bash
cd potions/mnq/v2d
python3 run_adaptive_50_150_scaleout.py
python3 run_adaptive_50_150_scaleout.py --export-csv ./adaptive_50_150_scaleout_legs.csv
```

Defaults:

- **`--adaptive-csv`** — `mnq_orb_results_adaptive_50_150.csv` (regenerate via `python3 build_adaptive_trades.py`).
- **`--1m`** — `mnq/raw/glbx-mdp3-20210304-20260303.ohlcv-1m.csv`

The script prints:

1. **Full stitched CSV** totals (all legs, **1 MNQ**, as recorded in the CSV).
2. **Paired subset** — CSV **Net_$** summed only over legs where the scale-out sim produced a fill + exit (same ordering as the equity curve used for scale-out).
3. **Scale-out sim** — **2 MNQ** totals, drawdowns, **Σ Net / |max DD leg|** on the paired path, and TP1/TP2 hit counts.

**Coverage caveat:** Some CSV legs may be **skipped** if the simplified **1 m** fill path never triggers (missing session data, subtle differences vs canonical step2 slip/OBC ordering). Treat skipped count in stdout as a reconciliation item; extend `--1m` date span or align slip rules if you need 100% row coverage.

---

## Snapshot (workspace defaults, single run)

Example output from `python3 run_adaptive_50_150_scaleout.py`:

| Book | Legs | Σ Net USD | Max DD (leg cum.) |
|------|------|-----------|-------------------|
| CSV full stitched | 1,919 | \$18,885 | −\$3,542 |
| CSV paired subset | 1,831 | \$17,178.50 | −\$3,535.50 |
| **Sim 2 MNQ scale-out (paired)** | **1,831** | **\$30,218.50** | **−\$7,498** |

Runner touches (paired): **TP1 hit 843 / 1,831**; **TP2 hit 330 / 1,831**.

Numbers drift if inputs change (DB end date, regenerated adaptive CSV, or different 1m file).

---

## Related

| Topic | Location |
|-------|----------|
| Stitching v2b \| v2d | `build_adaptive_trades.py` |
| Unified sim + children | `orb_adaptive_50_150_child.py` |
| Strategy index | `case_studies/STRATEGY_TRACKER.md` |
| v2b_m scale-out reference rules | `case_studies/v2b_m/v2b_m_so/README.md` |
