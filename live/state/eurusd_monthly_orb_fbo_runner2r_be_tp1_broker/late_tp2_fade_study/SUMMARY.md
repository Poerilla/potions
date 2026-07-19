# Study: fade late TP2 with 1/1/3 (SL at original 2R)

On promoted **1/1/3** book, for TP2 hits **at/after half-month**:

- Enter **fade** (opposite) at TP2 price
- **SL at original 2R** (→ **1R risk** on the fade)
- Same ladder **1 @ 0.25R / 1 @ 1R / 3 @ 2R**, BE after TP25, close-SL
- Management starts **next session** after TP2

Late TP2 campaigns: **36** (fadeable with ≥1 day left: **35**).

## Verdict

**Fade overlay alone is slightly negative (~−$5.9k).** Replacing the late runner with the fade is much worse: you give up ~+$141k of post-TP2 runner PnL for a ~−$6k fade book (**≈ −$147k** opportunity cost).

The fade often scrapes TP25 (**86%**) but rarely gets the meat (**1R 17% / 2R 6%**). Over half (**54%**) get stopped when price tags original 2R — exactly the path where the original runner prints.

| Metric | Fade (late TP2) | Keep post-TP2 runner |
|---|---:|---:|
| Net | **−$5,884** | **+$140,661** |
| WR | 45.7% | — |
| Avg / med | −$168 / −$254 | — |
| Closed DD | −$20,325 | — |
| Hit TP25 / 1R / 2R | 85.7% / 17.1% / 5.7% | — |
| Stopped thru 2R | 54.3% | (10/35 hit orig TP3) |

## Path split

| Bucket | n | Fade net | Orig runner after TP2 |
|---|---:|---:|---:|
| Stopped at 2R | 19 | −$53.2k | +$105.0k |
| Non-stopped (revert / me) | 16 | +$47.3k | +$35.7k |

When the fade *doesn't* get run over, it slightly beats holding the runner. The whole edge against fading is the continuation set: late TP2 → 2R still happens often enough (and large enough) that SL-at-2R fades pay for those runners.

CSV: `late_tp2_fade_trades.csv`
