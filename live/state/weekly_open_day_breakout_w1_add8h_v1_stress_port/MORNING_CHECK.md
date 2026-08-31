# Morning check — w1+8h v1 stress/port

Hub: `live/state/weekly_open_day_breakout_w1_add8h_v1_stress_port`
PID file: `run.pid` · logs: `PROGRESS.log` / `run.log`
DSR: `TRL-2026-00168` · contract: `RESEARCH_CONTRACT.yaml` (**max_adds=9**)

## Commands

```bash
PID=$(cat live/state/weekly_open_day_breakout_w1_add8h_v1_stress_port/run.pid)
ps -p $PID -o pid,etime,cmd
tail -40 live/state/weekly_open_day_breakout_w1_add8h_v1_stress_port/PROGRESS.log
cat live/state/weekly_open_day_breakout_w1_add8h_v1_stress_port/SUMMARY.md
cat live/state/weekly_open_day_breakout_w1_add8h_v1_stress_port/DECISION.json
```

## Expected artifacts

| Path | Meaning |
|---|---|
| `states/nas100_primary_v1/` | Frozen v1 strict replay |
| `states/nas100_base_no_adds/` | No-add baseline |
| `stage1_2/ATTRIBUTION.md` | Init vs adds, concentration, yearly |
| `states/nas100_stress_*/` | Execution stress matrix |
| `states/nas100_neigh_*/` | 6/8/10h · cap±1 · Fri 12/13/14 |
| `stage5_stats/` | Blocks, LOO, bootstrap |
| `states/{nq,mnq,ym,mym}_xmarket_v1/` | Frozen ports |
| `SUMMARY.md` / `EMAIL.txt` | Decision matrix + phone email |

## Primary snapshot (started overnight)

- net=$+25,211 · N/S=3.34 · trades=53 · adds=268 · units=427
- causality_violations=0 · feature_snapshots=6023 · max_open_units=12
- Matches discovery tape with max_adds locked at observed effective max (9)

Paper/demo: **NOT YET** per contract.
