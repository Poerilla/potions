# OANDA fault fixtures (curated)

Frozen reconstructions of Aug 13–14 practice-account incidents used to regression-test
daemon containment (`live/demo/oanda_daemon_reconcile.py`) and the offline fault-day
harness (`live/demo/oanda_fault_replay.py`).

**Do not point tests at live `live/demo/*/state/`** — those mutate. Each case has
`meta.json` provenance plus per-book `positions.csv` / `orders.csv` / `expected.json`.
Incident days also ship **real OANDA demo bar slices** under `bars/` (copied from
practice demo stores) so hardenings can be exercised against the same minutes that
ran live.

| Case | Fault | Expected action | Bars |
|------|-------|-----------------|------|
| `2026-08-13_stop_only_v2b` | Open qty=3, stop only | freeze_entries | NAS100/SPX500 1m (Aug 12 late + Aug 13) |
| `2026-08-14_orphan_stop_flat_v2b` | Flat + working stop | cancel_orphans | NAS100/SPX500 1m (Aug 13 late + Aug 14) |
| `2026-08-14_stream_hung_missed_entry` | Flat book + pricing stream stale ~4h | freeze_entries (DISARM) | NAS100 1m (Aug 14) |
| `2026-08-13_us30_3r_open_no_bracket` | Open, no working brackets | freeze_entries | (book only) |
| `2026-08-13_foreign_bleed_synthetic` | Foreign instruments in local positions | flat_for_day | (book only) |
| `qty_mismatch_hard` | Local +3 vs broker −3 | flat_for_day | (book only) |
| `healthy_protected_v2b` | Stop + TP coverage | none | (book only) |

## Run

```bash
# Detector + live-mode containment unit tests
python -m pytest live/tests/test_oanda_daemon_containment.py live/tests/test_oanda_fault_day_replay.py -q

# Offline fault-day harness (bar slice → inject book → containment)
PYTHONPATH=/home/tester/hsm:/home/tester/hsm/potions/v20-python/src \
  python -m potions.live.demo.oanda_fault_replay
PYTHONPATH=/home/tester/hsm:/home/tester/hsm/potions/v20-python/src \
  python -m potions.live.demo.oanda_fault_replay \
    --also-plugin-replay \
    --hub live/state/oanda_fault_replay_curated \
    --email
PYTHONPATH=/home/tester/hsm:/home/tester/hsm/potions/v20-python/src \
  python -m potions.live.demo.oanda_fault_replay --also-plugin-replay --case 2026-08-13_stop_only_v2b
```

Optional per-book `live_fills_that_day.csv` documents what the live daemon actually filled that day
(for missed-entry / orphan postmortems). The harness reports live vs plugin fill counts in the hub
`SUMMARY.md` without gating PASS/FAIL on fill parity.

## Curate a new case from a live demo

```python
from pathlib import Path
from potions.live.demo.oanda_fault_replay import curate_case_from_demo

curate_case_from_demo(
    demo_root=Path("live/demo/nas100_v2b_ungated_oanda"),
    case_name="YYYY-MM-DD_short_name",
    book_name="nas100",
    instrument="NAS100",
    strategy_id="nas100_v2b_ungated_oanda",
    strategy_type="v2b_scaleout",
    as_of="YYYY-MM-DDTHH:MM:SSZ",
    day="YYYY-MM-DD",
    classification="stop_only",  # or orphan_protective / qty_mismatch / ...
    recommended_action="freeze_entries",
)
```

Then fill `expected.json` / `meta.json` and add a row to this README.
