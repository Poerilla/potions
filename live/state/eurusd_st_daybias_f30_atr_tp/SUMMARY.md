# f30 week — ATR take-profit sweep (pandas)

Baseline hold = stop or Friday close. TP variants exit at **k × hourly ATR(14)**
from each lot's entry (campaign exits when nearest lot TP is tagged; stop still
pessimistic vs TP on the same bar).

Window 2015-01-01 → 2026-03-31. Unit = half-lot (PV $50k), fee $0.75.

## Broker vs pandas failure mode (why hold kills broker)

Matched would-be winners (research period_end +, broker −):
- **75%** are broker STOP while research PERIOD_END
- Broker hold median **~1h** vs research **~74h** on those paths
- MFE before broker stop: only **~0.65 ATR** — price never runs before the stop
- Share that reach k×ATR *before* broker stop: 1× **29%**, 2× **12%**, 3× **7%**, 4× **2%**, 5× **0%**

**Implication:** ATR TP does **not** fix the main broker failure mode. Those trades
die at the prev-day extreme before a 1–3 ATR run develops. TP can still change the
pandas book (bank winners earlier) but is unlikely to close the broker gap alone.

## Pandas TP leaderboard

| Strategy | TP | Net | Closed DD | Net/DD | WR | Med hold h | TP exits | Stop | Period |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| f30_week_no_tp | — | $32,406 | $-1,954 | 16.59 | 26.6% | 28.3 | 0 | 368 | 173 |
| f30_week_tp_4atr | 4×ATR | $24,562 | $-1,626 | 15.11 | 34.5% | 24.0 | 151 | 346 | 100 |
| f30_week_tp_5atr | 5×ATR | $23,540 | $-2,125 | 11.08 | 31.5% | 24.0 | 118 | 358 | 108 |
| f30_week_tp_3atr | 3×ATR | $20,982 | $-1,278 | 16.42 | 38.5% | 24.0 | 191 | 331 | 91 |
| f30_week_tp_2atr | 2×ATR | $9,950 | $-1,359 | 7.32 | 41.4% | 24.0 | 224 | 322 | 82 |
| f30_week_tp_1atr | 1×ATR | $-932 | $-2,300 | -0.41 | 46.8% | 23.9 | 275 | 302 | 69 |

## Broker stress (f30 week + ATR TP)

Engine / 1m fills / FX spread — confirms TP does not rescue the book:

| Variant | Net | Stress | Net/Stress | WR |
|---|---:|---:|---:|---:|
| no TP (prior) | −$590 | −$9.8k | −0.06 | 21.6% |
| 3×ATR TP | −$3.3k | −$6.3k | −0.53 | 31.3% |
| 4×ATR TP | −$1.5k | −$6.7k | −0.22 | 27.4% |

3×ATR raises WR but **worsens net** vs no-TP broker (cuts the rare runners without preventing early stops).

CSV: `leaderboard.csv` · broker: `broker/SUMMARY.md`
