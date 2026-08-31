# Quarterly ±4×ATR fade ladder — 1m fill tape

Engine + PaperBroker: **4h** signal bars (`broker_fills=False`, +4h shift); **1m** resting fills; MTM audit on **4h**.
10 lots; scale 2 off every +2 ATR through +8 ATR (tp1–tp4); then BE → EOQ (2 runners).

| Market | Path | Mode | Sides | Risk | 4h bars | Trades | Units | Net | Stress DD | N/S | 4h N/S | WR | PF | Stance |
|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| XAUUSD | nan | first_only | lower | 2.00×ATR | 36,439 | 26 | 260 | $336,733 | $-106,446 | 3.16 | 4.08 | 44.6% | 3.46 | weak — 1m degraded vs 4h |
| EURUSD | second_after_upper | second_only | lower | 2.00×ATR | 36,962 | 18 | 180 | $41,290 | $-65,576 | 0.63 | 2.44 | 26.7% | 1.55 | weak — 1m degraded vs 4h |

Hub: `/home/tester/hsm/potions/live/state/quarterly_atr4_fade_ladder_promising_1m_broker`

