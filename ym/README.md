# YM (Dow mini) data and charts

This folder holds **YM** daily CSVs (`ym_daily.csv`), yearly ORB case-study outputs, and a few **cross-asset** research charts that live next to YM data for convenience.

## MNQ + VX daily panel (`mnq_vx_daily_ma50_150.png`)

Single PNG: **top** — MNQ daily **close** with **50-** and **150-day** simple moving averages (from `mnq/mnq_daily.csv`); **bottom** — **VX** front-month daily **close** (from `vx/vx_front_daily.csv`). The x-axis is the **calendar overlap** of both series.

### Prerequisites

- **`mnq/mnq_daily.csv`** — already maintained in the repo for MNQ research.
- **`vx/vx_front_daily.csv`** — built from a Databento **ohlcv-1d** drop under `vx/raw/` (e.g. `xcbf-pitch-*.ohlcv-1d.dbn.zst` for **XCBF.PITCH** / **VX.FUT**).

The VX DBN is often **DBN version 3**. The default repo Python (**3.8** + `databento` 0.42) cannot decode v3. Use **Python 3.10+** with a current client once (user install):

```bash
/usr/bin/python3.10 -m pip install --user 'databento>=0.77'
```

### 1. Export VX front daily to CSV

From the repo root (`potions/`):

```bash
/usr/bin/python3.10 vx/export_vx_front_daily.py \
  --dbn vx/raw/xcbf-pitch-20181104-20260511.ohlcv-1d.dbn.zst \
  --out vx/vx_front_daily.csv
```

After you download a new batch zip into `vx/raw/`, point `--dbn` at the extracted `*.ohlcv-1d.dbn.zst` file.

### 2. Render the chart

Works with normal **`python3`** (pandas + matplotlib only):

```bash
cd ym
python3 plot_mnq_vx_daily_panel.py
```

Default output: **`ym/mnq_vx_daily_ma50_150.png`**.

Options:

| Flag | Meaning |
|------|--------|
| `--mnq-csv` | Default: `../mnq/mnq_daily.csv` |
| `--vx-csv` | Default: `../vx/vx_front_daily.csv` |
| `--out` | Output PNG path |
| `--start YYYY-MM-DD` | Optional lower date bound |
| `--figsize W,H` | Default `14,9` |
| `--dpi` | Default `120` |

## Other material here

- **`ym_daily.csv`** — YM daily OHLCV (same column style as `mnq/mnq_daily.csv`).
- **`case_studies/`** — e.g. ATR equity scaling and yearly ORB swing-stop studies; see each subfolder’s `README.md`.
