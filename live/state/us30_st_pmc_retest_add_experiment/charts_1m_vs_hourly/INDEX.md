# Hourly fill tape vs 1-minute fill tape

Same strategy (`sl50_tp150_3r`), same 1h Supertrend+PMC signals.
Only difference: broker fill resolution on **hourly OHLC** vs **1m bars after each signal hour**.

| # | Chart | What it proves |
|---:|---|---|
| 1 | [01_20181203.png](01_20181203.png) | H 09:00→09:00 (target) vs 1m 09:59→10:00 (stop) |
| 2 | [02_20181221.png](02_20181221.png) | H 10:00→10:00 (target) vs 1m 10:00→10:00 (target) |
| 3 | [03_20181206.png](03_20181206.png) | H 14:00→14:00 (target) vs 1m 14:01→14:46 (target) |
| 4 | [04_entry_delay_hist.png](04_entry_delay_hist.png) | Distribution of entry timing lag |
| 5 | [05_outcome_flips.png](05_outcome_flips.png) | Stop/target flips from path resolution |
