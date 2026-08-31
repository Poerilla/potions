# Structure-program ST — research path (to `scale_run`)

Session narrative: how we got from structure+ST analytic books to the
`structure_sl_scale_run` ladder and its StrategyPlugin / PaperBroker gate.

## 1. Starting point

15m swing structures (L-H-LL-HH / H-L-HH-LL), last-20 bull & bear lists, program
flip after 2 opposing takeouts, 1m SuperTrend break → limit at structure.

Variants explored under `live/state/structure_program_st/`:

| Variant | Idea | Analytic NQ takeaway |
|---------|------|----------------------|
| `core` | Limit at broken ST; SL at structure | Baseline |
| `structure_sl` | Limit at structure; fixed risk beyond | Risk sweeps |
| `structure_sl_scale` | 4ct, 2@1R→BE, 2@3R / ST flip | +$110k PF~2.8 @ risk 8 |
| `split15` (batch) | 15ct, 5@1R, 5@EOD, 5@6R | Best analytic: NQ r12 **+$1.77M PF~7.2** |

## 2. Broker-like reality check (split15)

`structure_program_st` StrategyPlugin + PaperBroker (`live/structure_program_st_replay.py`):

| ST-flip mode | NQ net | PF | Note |
|--------------|--------|-----|------|
| always | −$130k | 0.66 | Least bad |
| adverse only | −$204k | 0.56 | Worse — flips lock losses |
| after N=10 | −$232k | 0.59 | Behaves like off |
| off | −$247k | 0.58 | risk_stop dominates |

**Conclusion:** analytic split15 edge does **not** survive PaperBroker. ST-flip
exits (~80% of units when always-on) and risk stops destroy the book.

DSR: TRL-2026-00072 (NQ) and follow-ons.

## 3. “Would ST-flip have killed winners?”

Counterfactual on research ST-flip losers held without flip
(`st_flip_killed_winners/`): only **22** of 140 ST-flip exits would flip from
loss → win (Δ ~+$111k). Not enough alone to resurrect split15.

Separately, on **favourable** `structure_sl_scale` ST-flips (137): holding at BE
after the flip bar still reached **+100 on 41%** and **+200 on 23%** before BE
(`structure_sl_scale_run/GATE.md`). So ST-flip *does* truncate real runners —
worth a different exit design, not “always flatten”.

## 4. New plan: capture 200-pt moves

Hypothesis: if favourable ST-flip only tightens to BE (instead of closing), and
we scale in 5-contract batches at absolute targets, we can harvest large NQ days.

**`structure_sl_scale_run`** (analytic):

- Risk 8 pts beyond structure
- 15 contracts: **5 @ +22 · 5 @ +50 · 5 @ +200**
- Favourable ST-flip → stop to BE (hold); adverse ST-flip flattens
- No EOD flatten (overnight hold for runners)

Analytic NQ (2020+): **325 trades, +$2.03M, PF 9.6**, 64 full 200-pt runners.
Winners hit +25 / +100 / +200 at **96% / 61% / 40%** while open
(`extension_hits.csv`).

Caveat: still the research tape model until broker-like confirms.

## 5. Broker-like gate (this step)

- Plugin plan: `scale_run` on `structure_program_st` (`st_flip_mode=fav_be`)
- Driver: `python -m live.structure_program_st_replay --plan scale_run --risk-pts 8`
- Artifacts: `live/state/structure_program_st_broker_scale_run/`
- DSR: **TRL-2026-00079**

### Result (NQ full sample)

| | Analytic | PaperBroker |
|--|--:|--:|
| net | +$2.03M | **−$102.6k** |
| PF | 9.61 | **0.70** |
| trades | 325 | 228 |

**FAILS promotion.** Adverse `st_flip` (−$199k units) + `risk_stop` dominate;
only 20 runner units hit +200. Fav-ST→BE does not rescue the book under broker fills.

Promotion stance: parked / research-only unless a new exit design survives PaperBroker.

## 6. Entry parity & analytic-as-signal (2026-08-03)

See `live/state/structure_program_st_broker_scale_run/entry_parity/ENTRY_PARITY.md`.

Binding issue: PaperBroker **strict live_after** → entry on touch+1; strategy can ST-flip on entry bar → flatten next bar. ~70% of campaigns die in ≤1 minute; survivors are net positive.

Analytic-as-signal (TRL-2026-00080) and sweep_reclaim (TRL-2026-00081) both fail overall; reclaim improves survivor bucket only.

## 7. Structure-only resting (no ST entry) + v2b level align (2026-08-03)

**Resting limit @ structure without ST break** (`signal_source=structure_only`,
guards: one-shot / non-marketable / consume-key):

| | ST-gated scale_run | structure_only resting |
|--|--:|--:|
| net | −$103k | **−$2.13M** |
| PF | 0.70 | 0.185 |
| trades | 228 | 493 |
| hold≤1 $ | −$258k | −$2.55M |
| hold>1 $ | +$155k | +$421k |

**FAIL** (TRL-2026-00083). Dropping the ST arm adds more next-bar deaths.
Hub: `live/state/structure_program_st_broker_struct_v2/STRUCT_RESTING.md`.

**v2b / OR alignment** (`live/state/structure_program_st/v2b_align/`):
structure keys sit **against** the day's first break **77.6%** of the time;
when directions match, only ~**7%** of keys are in the 0–2R breakout band.
Median |key − v2b TP1| ≈ 285 pts. Resting at structure is **not** co-located
with v2b OR targets.

## 8. Touch-through → ST-align market (`touch_st_align`, 2026-08-03)

Flow: interact with structure key (touch + trade through) → wait for ST flip
aligned with program → **market** on flip; initial SL = new ST trail; at **+25**
scale 5 and tighten SL to **±12**; then 5@+50 / 5@+200; fav ST→BE.

| | Analytic | PaperBroker |
|--|--:|--:|
| trades | 1215 | 1391 |
| net | **+$1.37M** | **−$1.25M** |
| PF | 1.30 | 0.84 |
| win% | 57.7 | 45.1 (camp) / 31.5 (unit) |

Analytic looked promising (all years green except 2026). Broker **FAIL**
(TRL-2026-00084). Notably hold≤1 is only ~1% (entry after ST flip removes most
next-bar deaths) — losses are in the managed book / adverse ST + risk stops.
Hub: `live/state/structure_program_st_broker_touch_align/`.

### Structural invalidity (entry vs structure key)

Day-key audit (`…/invalid_audit/`): **~37%** of broker fills are still through
the structure at entry (**30% deep ≥25 pts**). Through bucket net **−$651k**;
reclaimed also **−$582k**. So buying/selling the broken level is a large share
of damage, but not the only hole.

### fade20 (through ≥20m → fade limit @ key ±25)

| | Analytic | PaperBroker |
|--|--:|--:|
| net | +$670k PF 1.34 | **−$871k PF 0.75** |
| trades | 670 | 922 |

Broker split: fade limits **−$593k** (WR 10%) · continuation markets **−$278k**
(WR 45%). Better than plain touch_align (−$1.25M) but still **FAIL**
(TRL-2026-00085). Hub: `live/state/structure_program_st_broker_touch_align_fade20/`.

## 9. Structure VWAP split scale-in (`vwap_scalein`, 2026-08-04)

Idea: while program is active, **scale into** the structure with spaced session-VWAP
limits (5×3ct, ≤1 slice per 15m); SL at structure extreme (LL long / HH short);
re-arm only after a **15m close back inside** after a structure stop-out; ladder
5@+25→±12 / 5@+50 / 5@+200; fav ST→BE; **RTH 15:59 flatten**.

| | Analytic | PaperBroker |
|--|--:|--:|
| trades | 13898 | 267 camps / 909 units |
| net | **−$6.44M** | **−$1.11M** |
| PF | 0.171 | 0.044 |
| win% | 2.9 | 12.5 |
| avg slices | 1.14 (0.9% full 15) | — |

Most analytic campaigns die on 1-slice `st_flip` / `structure_stop`. Full size
almost never builds. Broker is even worse on PF. **FAIL** (TRL-2026-00086).
Hubs: `live/state/structure_program_st/vwap_scalein/`,
`live/state/structure_program_st_broker_vwap_scalein/`.

Family remains **PARKED**.
