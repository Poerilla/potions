# EURUSD Overnight Runs — Morning Checklist

Unattended broker-like StrategyPlugin sweeps on Histdata EURUSD.

## Where to look first

1. **Main ranked leaderboard**  
   [`live/state/eurusd_overnight_sweep/SUMMARY.md`](eurusd_overnight_sweep/SUMMARY.md)  
   Live progress: [`PROGRESS.log`](eurusd_overnight_sweep/PROGRESS.log)

2. **Prior opposed (already finished earlier tonight)**  
   [`live/state/eurusd_v2b_prior_opposed_stpmc_broker_like/INDEX.md`](eurusd_v2b_prior_opposed_stpmc_broker_like/INDEX.md)

3. **Extras (WO gap + weekly-mid MA500)**  
   [`live/state/eurusd_overnight_extras/PROGRESS.log`](eurusd_overnight_extras/PROGRESS.log)

## Tracker systems covered

| Family | Source rank / note | EURUSD adaptation |
|---|---|---|
| Yearly ORB scaleout3 | Broker-like #1–4 | Daily, unchanged rules |
| Yearly ORB 20% range-close | Institutional top-10 | Daily OCO variant |
| ATR daily ladder / 3-initial / weekly | Best ATR shapes | Daily ATR Supertrend DCA |
| Monthly ORB restricted | Broker-like table | Both limit + boundary-stop |
| Hourly ST+PMC 25/75, 40/120, 50/150 | Top hourly sleeves | **Pips** (0.0025 / 0.0040 / 0.0050) |
| v2b OCO `S_1_1_3` + `1/0/0` | Flagship all-day sizes | NY RTH 1m, FX tick/spread |
| Prior-opposed ST→v2b | Allocator #1 family | Already banked (Net −$9.5k from 2015) |
| WO gap + weekly mid | Secondary research | Pip-scaled companions |

## Early daily read (already banked in smoke + main)

From the first daily pass:

- **Yearly ORB scaleout3: $165,865 net / Net/Stress 8.31** — clear EURUSD leader so far
- Yearly ORB 20% range-close: $124,519 / 2.60
- ATR expressions and prior-opposed were **negative** on this FX tape in the first pass

## Process / resume

```bash
# Main sweep status
tail -f live/state/eurusd_overnight_sweep/PROGRESS.log

# If Python died, resume without wiping finished daily state is not automatic;
# re-run full:
python3 -m live.eurusd_overnight_sweep --output-root live/state/eurusd_overnight_sweep
```

Assumptions: timestamps localized as America/New_York; 1 standard lot; $7/unit fee proxy; ~0.5 pip half-spread on 1m rows.
