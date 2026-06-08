# v2b_m_child

Experimental **scale-in** on top of the main **v2b_m** filter (long-only, `bullish_break`, prior-month-high OR geometry, no hemisphere).

- **Tier‑1:** simulated buy-stop breakout **`RH + tick`** after OR, **SL RL**, **TP RH + Range**, **1 MNQ**.
- **Child:** after tier‑1 fill, first completed **5 m** RTH bar **after** that timestamp whose **O/H/L/C are all above RH**; arm a **limit buy at that bar’s open**; if filled, **+1 MNQ** with **SL at RH** (opening-range **high**; tier‑1 still uses **RL**). Shared **TP RH + Range** flats remaining size.

See **`run_v2b_m_child.py`** docstring for ordering assumptions (`\$2`/pt, `\$1.50`/MNQ round-trip per closed contract).

```bash
cd potions/mnq/case_studies/v2b_m_child
python3 run_v2b_m_child.py --export-csv ./v2b_m_child_compare.csv
```

Output prints three columns: **historical tier‑1 CSV** (`mnq_orb_results_stops` filtered), **simulated tier‑1 only**, **simulated tier‑1 + child** — same qualified calendar dates where tier‑1 sim fills.

The authoritative definition of **v2b_m** remains **`../v2b_m/`** (`engine.py` + tier‑1 CSV book).
