# Yearly first-month ±4×ATR fade (FX/metals)

Engine + PaperBroker on **daily** bars. January mean daily TR is the first-month ATR.
After January completes, fade first touch of **anchor ± 4×ATR**. 2 lots; 1@anchor +
runner@opposite; reverse once; risk 2×ATR; flatten at year change.

Causal market entry/flatten: `live_after_ts=decision_bar.ts` (next daily open).
Realism: `slippage_ticks=1`, metals $1.50/unit, AUDJPY ¥7/unit. AUDJPY ~USD uses ÷110.

Rank by Net/Stress. Research / not promotion-safe.

| Rank | Market | Book | Trades | Units | Net | Stress DD | N/S | WR |
|---:|---|---|---:|---:|---:|---:|---:|---:|
| 1 | AUDJPY | year-open ±4×Jan mean TR | 27 | 54 | ¥1,416,220 (~$12,874.73) | ¥-3,271,186 | 0.43 | 24.1% |
| 2 | XAGUSD | Jan mid ±4×Jan mean TR | 25 | 50 | $8,142.23 | $-34,974.77 | 0.23 | 14.0% |
| 3 | AUDJPY | Jan mid ±4×Jan mean TR | 27 | 54 | ¥49,806 (~$452.78) | ¥-4,053,102 | 0.01 | 22.2% |
| 4 | XAUUSD | Jan mid ±4×Jan mean TR | 24 | 48 | $-54,632.36 | $-138,168.91 | -0.40 | 14.6% |
| 5 | XAUUSD | year-open ±4×Jan mean TR | 28 | 56 | $-58,236.84 | $-105,073.42 | -0.55 | 25.0% |
| 6 | XAGUSD | year-open ±4×Jan mean TR | 25 | 50 | $-25,464.85 | $-26,890.22 | -0.95 | 12.0% |

## Per-market

### AUDJPY

- **year-open ±4×Jan mean TR** N/S=0.43 net=¥1,416,220 stress=¥-3,271,186 trades=27 units=54 WR=24.1% (~$12,874.73 / $-29,738.06 @110)
- **Jan mid ±4×Jan mean TR** N/S=0.01 net=¥49,806 stress=¥-4,053,102 trades=27 units=54 WR=22.2% (~$452.78 / $-36,846.38 @110)

### XAGUSD

- **Jan mid ±4×Jan mean TR** N/S=0.23 net=$8,142.23 stress=$-34,974.77 trades=25 units=50 WR=14.0%
- **year-open ±4×Jan mean TR** N/S=-0.95 net=$-25,464.85 stress=$-26,890.22 trades=25 units=50 WR=12.0%

### XAUUSD

- **Jan mid ±4×Jan mean TR** N/S=-0.40 net=$-54,632.36 stress=$-138,168.91 trades=24 units=48 WR=14.6%
- **year-open ±4×Jan mean TR** N/S=-0.55 net=$-58,236.84 stress=$-105,073.42 trades=28 units=56 WR=25.0%

Hub: `live/state/yearly_atr4_fade_fx_metals`

## Vs yearly ORB breakout (same names, exit-variant pack)

| Market | Fade best N/S | ORB best N/S (exit pack) | Fade vs ORB |
|---|---:|---:|---|
| AUDJPY | 0.43 year-open | −0.02 (4/1/1 mid-close) | Fade better; both weak |
| XAGUSD | 0.23 Jan-mid | 1.29 (4/2/1 range-close) | ORB breakout wins |
| XAUUSD | −0.40 Jan-mid | 4.58 (1/3/3 mid-close) | Fade rejected; gold trends |

Gold/silver 4×ATR extensions from the first month are **not** a fade edge. AUDJPY year-open ±4×Jan ATR is the only modestly positive fade book (N/S 0.43, WR 24%, ~$13k net vs ~$30k stress).

Stance: **not a pack-wide base**. Keep metals on yearly ORB breakout. AUDJPY fade is research-only (low WR, stress ≫ net); needs yearly split + causality before any follow-up.

