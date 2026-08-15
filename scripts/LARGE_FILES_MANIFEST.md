# Large files archive (curated)

List: `scripts/large_files_to_strip.txt`  
Pack: `scripts/pack_large_files.sh` → `data/potions_large_files.tar.zst` + `.manifest`  
Unpack: `scripts/unpack_large_files.sh`

## Why this set

Irreplaceable **raw market data** plus **winner-path results** needed to rebuild portfolio products and institutional metrics. Full sweep dumps, `feature_snapshots.csv`, chart packs, and losing-tag audits are **excluded** (regenerable or disposable).

## Included

| Class | Paths | Notes |
|-------|--------|--------|
| Futures raw | `nq/mnq/es/ym/mym/vx/mes/raw` | Prefer `.dbn.zst` / purchase zips; skip extracted `ohlcv-1m.csv` when a zip/dbn sibling exists |
| FX raw | `fx/raw/*.{txt,zip}` | Vendor ticks / purchase zips |
| FX 1m | `fx/*_1m.csv` | Convenience restore (rebuildable from raw) |
| Benchmarks | `data/benchmarks/*` | Shared reference series |
| Monday OR winners | Phase 1/2 tags under `live/state/monday_or_*` | Equity/fills/summaries only; no feature dumps |
| Prior-opposed resting-limit | NQ/MNQ/YM/MYM/ES winner equities | Tracker / institutional inputs |
| Broker-like / FX-metals leaders | Selected equities + summaries | Yearly ORB, FBO, ST+PMC |
| Portfolio products | `portfolio_product_tiers`, `target_10pct_portfolio`, `institutional_strategy_metrics` | Tier CSVs + summaries |

## Excluded (intentionally)

- `feature_snapshots.csv` and other multi-GB order/state dumps  
- Full losing-tag Monday OR / sweep audits  
- Chart image packs and transient logs  
- Anything already small enough to live in git

## Restore

```bash
./scripts/unpack_large_files.sh data/potions_large_files.tar.zst
```

Does **not** delete local files when packing; packing only creates/overwrites the archive + sidecar manifest.
