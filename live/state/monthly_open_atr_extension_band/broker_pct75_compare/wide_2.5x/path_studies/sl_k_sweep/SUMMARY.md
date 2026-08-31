# SL k sweep (wide_Nx) — do wider stops pay?

Stop: `SL = band_max + k·(band_max − entry)`. Same pct75 entries as broker wide_2.5x fills.
Sweep **k ∈ {1.5, 2.0, 2.5, 3.0, 3.5, 4.0}**. Qty 10, fee $1.50/unit/side, target=month open, EOM flatten.
Trades: **73** (fill-paired with plan). Broker wide_2.5x audit net $607,969.

## All weeks

| k | Wins | Win% | Stops | Net $ | Δ vs 2.5 | New winners | Lost winners | Gain from improved | Loss from worsened | Wider stops win? |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|:---:|
| 1.5 | 33 | 45.2% | 30 | 551,104 | -243,813 | 0 | 6 | +349,222 | -593,035 | NO |
| 2.0 | 37 | 50.7% | 23 | 786,879 | -8,038 | 0 | 2 | +167,232 | -175,271 | NO |
| 2.5 | 39 | 53.4% | 18 | 794,917 | +0 | 0 | 0 | +0 | +0 | yes |
| 3.0 | 39 | 53.4% | 14 | 742,225 | -52,693 | 0 | 0 | +88,997 | -141,690 | NO |
| 3.5 | 39 | 53.4% | 13 | 684,935 | -109,983 | 0 | 0 | +144,386 | -254,369 | NO |
| 4.0 | 39 | 53.4% | 12 | 675,806 | -119,111 | 0 | 0 | +187,421 | -306,532 | NO |

## No week 4

| k | Wins | Win% | Stops | Net $ | Δ vs 2.5 | New winners | Gain improved | Loss worsened | Wider OK? |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|:---:|
| 1.5 | 28 | 48.3% | 25 | 627,885 | -262,642 | 0 | +285,369 | -548,011 | NO |
| 2.0 | 31 | 53.4% | 20 | 850,562 | -39,965 | 0 | +135,306 | -175,271 | NO |
| 2.5 | 33 | 56.9% | 15 | 890,527 | +0 | 0 | +0 | +0 | yes |
| 3.0 | 33 | 56.9% | 13 | 766,868 | -123,659 | 0 | +3,525 | -127,184 | NO |
| 3.5 | 33 | 56.9% | 13 | 639,684 | -250,843 | 0 | +3,525 | -254,369 | NO |
| 4.0 | 33 | 56.9% | 12 | 630,555 | -259,972 | 0 | +46,560 | -306,532 | NO |

## Verdict

- Best net in sweep: **k=2.5** at **$794,917** (39 wins).
- **k=3.0 vs 2.5**: Δ **$-52,693** · new winners **0** · gain from improved **$+88,997** vs deeper/worsened **$-141,690** → deeper losses dominate.
- Avg loss at k=2.5: **$-45,751** · at k=3.0: **$-47,301**.

Diagnostic pandas path study (not Engine). Compare to broker only at k=2.5.
Hub: `/home/tester/hsm/potions/live/state/monthly_open_atr_extension_band/broker_pct75_compare/wide_2.5x/path_studies/sl_k_sweep`

