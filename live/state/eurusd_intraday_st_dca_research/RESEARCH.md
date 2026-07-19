# EURUSD 15m SuperTrend DCA — research pause pack

**Status:** Paused (2026-07-18)  
**Verdict:** Not an upgrade to the FX intraday baseline. Useful negative result + close-exit improvement.

## What was tested

| Book | Path | Result |
|---|---|---|
| 15m ST DCA (wick trail stop) | Engine + PaperBroker | −$516.5k / −$517.8k stress / Net/Stress −1.0 |
| 15m ST DCA (**close-beyond-trail**) | Engine + PaperBroker | −$435.4k / −$436.7k stress / Net/Stress −1.0 |
| Fade-on-flip DCA (1R to new ST) | Engine + PaperBroker | −$287.4k / −$293.2k stress / Net/Stress −0.98 |
| Filters (week mid ±, MA50/150 ±) | Pandas sweep | All still negative; best follow was week-mid **opposite** (−$72k closed-DD path) |

Pandas research initially showed ~+$337k for 15m ST DCA with closed-equity DD only — that did **not** survive broker-like stress with add-lot accounting.

## Rules (paused books)

- Session: London 08:00 → NY 16:00
- Unit: 0.5 lot (PV $50k), fee $0.75/unit, up to 5 adds
- Follow: ATR ST 14×3; DCA each 15m while side holds; exit on trail (wick vs close)
- Fade: on ST flip, fade toward new trail with 1R stop

## Artifact locations

| Artifact | Path |
|---|---|
| Wick-stop broker (pre-close fix) | `../eurusd_intraday_st_dca_broker/` (overwritten by close-exit later) |
| Close-beyond-trail broker + charts | `../eurusd_intraday_st_dca_broker/` |
| Fade broker | `../eurusd_intraday_st_fade_dca_broker/` |
| Filter sweep | `../eurusd_intraday_st_dca_filters/` |
| Pandas MA/ST scout | `../eurusd_intraday_ma_st_research/` |
| Plugins | `../../strategies/intraday_st_dca.py`, `intraday_st_fade_dca.py` |
| Drivers | `../../eurusd_intraday_st_dca_replay.py`, `*_fade_*`, `*_filter_sweep.py`, `*_charts.py` |

## Takeaways kept

1. **Always count `add` fills as open lots** in `replay_audit.units_from_live_fills` (fixed).
2. **Close-beyond-trail** improves follow vs wick stops (~$80k less damage) but does not flip sign.
3. Weekly-mid / MA filters shrink losses; none clear FX baseline bar (~+$23.5k / 1.5 Net/Stress).
4. Bringing DCA onto the promoted hourly ST+PMC baseline **does not boost it** (see below).

## FX baseline + DCA (follow-up, 2026-07-18)

Same geometry as promoted pack (no FX spread overlay). ST-retest limit adds while thesis holds:

| max_adds | Net | Stress DD | Net/Stress |
|---:|---:|---:|---:|
| 1 (baseline) | **+$23,534** | **−$15,745** | **1.49** |
| 2 | +$20,940 | −$26,247 | 0.80 |
| 3 | +$17,316 | −$30,837 | 0.56 |
| 5 | +$14,331 | −$32,893 | 0.44 |

DCA adds size and stress faster than net — **keep single-unit baseline**.  
Artifacts: `../eurusd_baseline_dca_nospread/`

## FX baseline (unchanged / still promoted)

`../eurusd_forex_intraday_baseline/` — `eurusd_hourly_st_pmc_sl25_tp75_3r_ma_bull_prior`
