# REMOVED — NAS100 clean-break ma_aligned HP ×4 paper demo

**Removed:** 2026-09-13  
**Daemon stopped:** yes (was `demo-nas100-clean-break-ma-aligned-hp-x4-paper`)  
**CLI / runner deleted:** `live/cli.py` parsers + `live/demo/nas100_v2b_clean_break_trail_ma_aligned_hp_x4_paper.py`

## Why

Arm-asof `ma_aligned` HP @ **×4** does **not** meet size-up criteria — not even as a discretionary paper sleeve.

Evidence (`live/state/nas100_clean_break_ma_aligned_size15_broker/nulls_x4/`, DSR `TRL-2026-00202`):

| Gate | Result |
|------|--------|
| Decision | **NOT VALIDATED** |
| HP coverage | 55.5% (too broad for SIZE-UP VALIDATED / discretionary alpha claim) |
| `p_master_ΔNS` | **0.860** (fails ≫ 0.10 RISK THROTTLE line; far from BORDERLINE PAPER ≤0.10) |
| Placebo / shift `p_ΔNS` | 0.255 / 0.164 — incremental sleeve does not beat matched random exposure |

Engine tape can show higher whole-book N/S at ×4 (`~$40.8k / −$5.3k / 7.64` on the research unit), but matched-added-exposure nulls say that lift is **not** superior selection — do not run paper validation or route to OANDA.

**Ops stance:** Index Momentum stays on default clean-break base **10×** (`trail06_m4_e2_out_be` practice `-003`) with **no** ma_aligned HP size-up.

Frozen run artifacts under this directory are historical only — do not restart.
