# Quarterly ±4×ATR fade ladder (broker-like)

Engine + PaperBroker on **4h** bars. Open-week mid ±4×ATR(14).
10 lots; scale 2 off every +2 ATR through +8 ATR (tp1–tp4); then BE → EOQ (2 runners).
Mode / sides / risk come from per-market book (family default or best-path).

| Market | Path | Mode | Sides | Risk | Bars | Trades | Units | Net | Stress DD | N/S | WR | PF |
|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| US30 | second_after_upper | second_only | lower | 2.50×ATR | 13,668 | 5 | 50 | $7,088 | $-11,104 | 0.64 | 52.0% | 2.02 |

Hub: `live/state/quarterly_atr4_fade_ladder_us30_second_after_upper`

Promote gate: research until causality audit + multi-year N/S hold.
