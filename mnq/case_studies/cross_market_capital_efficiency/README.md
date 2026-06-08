# Cross-Market Capital Efficiency

> **Legacy ATR warning.** The ATR weekly-primary and weekly-filter rows in this report were generated before the 2026-05-08 Pine parity correction. A weekly ATR mapper bug caused some Python paths to inherit daily ATR columns. Treat the ATR ranking tables below as stale until all markets are rerun with the fixed mapper. The yearly ORB table is not affected by this ATR bug.

Scope: ATR Supertrend daily/weekly 10-max entry-guard variants and the current top yearly ORB candidate (`scaleout3 / inside-range swing stop / range-close`).

Capital rule for dynamic rows: at each calendar-year start, use the largest size allowed by the **3x full-sample MTM/stress DD** requirement. ATR uses the existing `--max-bump 40` cap, so peak max stack is 50 contracts/units. Yearly ORB uses bundles where one bundle is the 3-unit scaleout ladder.

Point values: MNQ $2/pt, NQ $20/pt, MYM $0.50/pt, YM $5/pt, ES $50/pt.

Data note: the YM daily ZIP present in `ym/raw` contains ES/MNQ daily symbols, so `ym_daily.csv` was derived from the valid YM 1-minute file using highest-volume outright per UTC date. Treat YM as comparable but slightly less pristine until a native YM daily DBN is downloaded.

## Fresh ES/YM ATR Results

| Market | Variant | Start Cap | Dynamic Net | Dynamic MTM DD | End/Start | Net/DD | Peak Contracts | Base Net | Base MTM DD |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| ES | Daily primary, 3-initial | $381,862 | $2,846,638 | $-551,250 | 8.45x | 5.16 | 33 | $1,343,562 | $-127,288 |
| ES | Daily primary, ladder 1/1/2/2/2 | $194,212 | $2,572,525 | $-413,438 | 14.25x | 6.22 | 30 | $1,195,188 | $-64,738 |
| ES | Weekly primary, 3-initial | $342,825 | $9,167,288 | $-858,488 | 27.74x | 10.68 | 50 | $1,998,225 | $-114,275 |
| ES | Weekly primary, ladder 1/1/2/2/2 | $201,825 | $6,652,950 | $-557,100 | 33.96x | 11.94 | 50 | $1,587,612 | $-67,275 |
| YM | Daily primary, 3-initial | $241,875 | $3,230,795 | $-522,310 | 14.36x | 6.19 | 50 | $831,220 | $-80,625 |
| YM | Daily primary, ladder 1/1/2/2/2 | $255,135 | $3,461,260 | $-540,210 | 14.57x | 6.41 | 50 | $626,150 | $-85,045 |
| YM | Weekly primary, 3-initial | $223,500 | $11,956,060 | $-573,835 | 54.49x | 20.84 | 50 | $1,431,265 | $-74,500 |
| YM | Weekly primary, ladder 1/1/2/2/2 | $252,060 | $11,009,240 | $-547,145 | 44.68x | 20.12 | 50 | $948,930 | $-84,020 |

## ATR Capital-Efficiency Leaders

| Market | Variant | Start Cap | Dynamic Net | Dynamic MTM DD | End/Start | Net/DD | Peak Contracts | Base Net | Base MTM DD |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| YM | Weekly primary, 3-initial | $223,500 | $11,956,060 | $-573,835 | 54.49x | 20.84 | 50 | $1,431,265 | $-74,500 |
| YM | Weekly primary, ladder 1/1/2/2/2 | $252,060 | $11,009,240 | $-547,145 | 44.68x | 20.12 | 50 | $948,930 | $-84,020 |
| NQ | Weekly primary, 3-initial | $370,125 | $20,896,810 | $-1,589,685 | 57.46x | 13.15 | 50 | $3,641,125 | $-123,375 |
| NQ | Weekly primary, ladder 1/1/2/2/2 | $384,600 | $18,477,275 | $-1,416,615 | 49.04x | 13.04 | 50 | $3,044,840 | $-128,200 |
| ES | Weekly primary, ladder 1/1/2/2/2 | $201,825 | $6,652,950 | $-557,100 | 33.96x | 11.94 | 50 | $1,587,612 | $-67,275 |
| MYM | Weekly primary, 3-initial | $21,874 | $560,260 | $-50,546 | 26.61x | 11.08 | 50 | $81,587 | $-7,292 |
| ES | Weekly primary, 3-initial | $342,825 | $9,167,288 | $-858,488 | 27.74x | 10.68 | 50 | $1,998,225 | $-114,275 |
| MYM | Weekly primary, ladder 1/1/2/2/2 | $24,690 | $434,118 | $-48,196 | 18.58x | 9.01 | 50 | $43,638 | $-8,230 |
| NQ | Daily primary, 3-initial | $467,505 | $9,841,690 | $-1,361,165 | 22.05x | 7.23 | 50 | $2,739,985 | $-155,835 |
| NQ | Daily primary, ladder 1/1/2/2/2 | $384,600 | $9,203,280 | $-1,297,855 | 24.93x | 7.09 | 50 | $2,556,810 | $-128,200 |
| YM | Daily primary, ladder 1/1/2/2/2 | $255,135 | $3,461,260 | $-540,210 | 14.57x | 6.41 | 50 | $626,150 | $-85,045 |
| ES | Daily primary, ladder 1/1/2/2/2 | $194,212 | $2,572,525 | $-413,438 | 14.25x | 6.22 | 30 | $1,195,188 | $-64,738 |

## Yearly ORB Scaling

| Market | Base Trades | Base Net | Base Stress DD | Start Cap | Dynamic Net | Dynamic Stress DD | End/Start | Net/Stress DD | Peak Bundles | Peak Contracts |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| YM | 87 | $258,816 | $-24,226 | $72,679 | $890,201 | $-86,580 | 13.25x | 10.28 | 8 | 24 |
| MNQ | 26 | $68,082 | $-4,604 | $13,812 | $299,667 | $-35,800 | 22.70x | 8.37 | 10 | 30 |
| MYM | 30 | $16,949 | $-2,357 | $7,071 | $29,752 | $-3,786 | 5.21x | 7.86 | 3 | 9 |
| ES | 81 | $441,669 | $-36,394 | $109,181 | $-11,153 | $-15,641 | 0.90x | -0.71 | 1 | 3 |
| NQ | 71 | $758,754 | $-45,165 | $135,495 | $-10,279 | $-12,814 | 0.92x | -0.80 | 1 | 3 |

## Read

- The fresh ES/YM ATR run supports the same pattern we saw on NQ/MNQ/MYM: weekly-primary beats daily-primary for capital efficiency.
- YM weekly-primary 3-initial is the strongest fresh ES/YM result by return multiple and net/DD. It is materially better than ES on the same framework.
- ES weekly-primary variants are profitable but require large starting capital and have larger absolute drawdown. ES yearly ORB is not attractive under the strict 3x start rule; it loses in the first year and does not recover because it stays at one bundle.
- YM yearly ORB is much stronger than ES yearly ORB and scales to 8 bundles, but its dynamic stress DD is still far larger than MYM/MNQ. It belongs in the “interesting, capital-heavy” bucket, not the first automation-test bucket.
- The most practical first live-test stack is **MYM ATR weekly-primary 3-initial** by itself. Start there if the goal is clean execution evidence. YM full-size is impressive but much less forgiving for automation testing, and MNQ/MYM combinations should be treated as later portfolio expansion rather than the first test.
