# Yearly ORB Scaleout3 Sizing Sweep — All 6 Markets

Combined output of two runs:
- `live/state/yearly_orb_sizing_sweep/` (MNQ, NQ — full 19-scenario grid)
- `live/state/yearly_orb_sizing_sweep_micro/` (ES, MES, YM, MYM — same grid)

Realism baseline: slippage=1 tick, fee=$1.50/RT, stop gap-through ON, stop-first same-bar, OCO-collapsed risk.

## Best sizing per market (by Net / Stress DD)

| Market | Best sizing | Init (TP25 / TP / Runner) | Total | Net | Stress DD | Net / DD |
|---|---|---|---:|---:|---:|---:|
| NQ | limit_retest 4/1/1 | 4 / 1 / 1 | 6 | $1,417,383 | $-128,766 | 11.01 |
| ES | limit_retest 4/2/1 | 4 / 2 / 1 | 7 | $657,146 | $-66,346 | 9.90 |
| MNQ | limit_retest 4/1/1 | 4 / 1 / 1 | 6 | $108,526 | $-12,850 | 8.45 |
| YM | limit_retest 4/1/1 | 4 / 1 / 1 | 6 | $515,736 | $-67,525 | 7.64 |
| MYM | limit_retest 4/1/1 | 4 / 1 / 1 | 6 | $28,376 | $-4,977 | 5.70 |
| MES | oco_stop 1/1/1 + 20% range-close | 1 / 1 / 1 | 3 | $9,878 | $-8,546 | 1.16 |

## User's pick `4 / 2 / 1` per market

| Market | Total | Net | Stress DD | Net / DD | vs baseline |
|---|---:|---:|---:|---:|---:|
| ES | 7 | $657,146 | $-66,346 | 9.90 | +1.76 vs baseline (8.14) |
| MES | 7 | $4,240 | $-6,671 | 0.64 | -0.04 vs baseline (0.68) |
| MNQ | 7 | $134,406 | $-17,007 | 7.90 | +1.53 vs baseline (6.37) |
| MYM | 7 | $33,860 | $-6,327 | 5.35 | +1.49 vs baseline (3.86) |
| NQ | 7 | $1,731,806 | $-169,810 | 10.20 | +2.23 vs baseline (7.97) |
| YM | 7 | $621,574 | $-81,932 | 7.59 | +0.34 vs baseline (7.25) |

## Full ranking (all rows across markets)

| Rank | Market | Sizing | TP25 | TP | Runner | Total | Entry | RC | Net | Stress DD | Net / DD |
|---:|---|---|---:|---:|---:|---:|---|---|---:|---:|---:|
| 1 | NQ | limit_retest 4/1/1 | 4 | 1 | 1 | 6 | limit_retest | — | $1,417,383 | $-128,766 | 11.01 |
| 2 | NQ | limit_retest 5/2/1 | 5 | 2 | 1 | 8 | limit_retest | — | $1,920,829 | $-179,992 | 10.67 |
| 3 | NQ | limit_retest 4/2/1 | 4 | 2 | 1 | 7 | limit_retest | — | $1,731,806 | $-169,810 | 10.20 |
| 4 | ES | limit_retest 4/2/1 | 4 | 2 | 1 | 7 | limit_retest | — | $657,146 | $-66,346 | 9.90 |
| 5 | ES | limit_retest 2/1/1 | 2 | 1 | 1 | 4 | limit_retest | — | $395,774 | $-41,103 | 9.63 |
| 6 | ES | limit_retest 4/2/2 | 4 | 2 | 2 | 8 | limit_retest | — | $791,549 | $-82,206 | 9.63 |
| 7 | NQ | limit_retest 2/1/1 | 2 | 1 | 1 | 4 | limit_retest | — | $1,039,337 | $-108,283 | 9.60 |
| 8 | NQ | limit_retest 4/2/2 | 4 | 2 | 2 | 8 | limit_retest | — | $2,078,674 | $-216,566 | 9.60 |
| 9 | ES | limit_retest 3/2/1 | 3 | 2 | 1 | 6 | limit_retest | — | $590,099 | $-61,654 | 9.57 |
| 10 | ES | limit_retest 5/2/1 | 5 | 2 | 1 | 8 | limit_retest | — | $724,193 | $-75,824 | 9.55 |
| 11 | NQ | limit_retest 3/2/1 | 3 | 2 | 1 | 6 | limit_retest | — | $1,542,783 | $-162,424 | 9.50 |
| 12 | ES | limit_retest 4/1/1 | 4 | 1 | 1 | 6 | limit_retest | — | $529,868 | $-56,868 | 9.32 |
| 13 | NQ | limit_retest 3/1/3 | 3 | 1 | 3 | 7 | limit_retest | — | $1,922,096 | $-213,440 | 9.01 |
| 14 | ES | limit_retest 3/1/3 | 3 | 1 | 3 | 7 | limit_retest | — | $731,627 | $-81,506 | 8.98 |
| 15 | MNQ | limit_retest 4/1/1 | 4 | 1 | 1 | 6 | limit_retest | — | $108,526 | $-12,850 | 8.45 |
| 16 | MNQ | limit_retest 5/2/1 | 5 | 2 | 1 | 8 | limit_retest | — | $147,934 | $-17,965 | 8.23 |
| 17 | ES | limit_retest 2/2/2 | 2 | 2 | 2 | 6 | limit_retest | — | $657,456 | $-80,806 | 8.14 |
| 18 | ES | limit_retest 1/1/1 (baseline) | 1 | 1 | 1 | 3 | limit_retest | — | $328,728 | $-40,403 | 8.14 |
| 19 | ES | limit_retest 3/3/3 | 3 | 3 | 3 | 9 | limit_retest | — | $986,183 | $-121,209 | 8.14 |
| 20 | NQ | limit_retest 1/1/1 (baseline) | 1 | 1 | 1 | 3 | limit_retest | — | $850,314 | $-106,720 | 7.97 |
| 21 | NQ | limit_retest 2/2/2 | 2 | 2 | 2 | 6 | limit_retest | — | $1,700,628 | $-213,440 | 7.97 |
| 22 | NQ | limit_retest 3/3/3 | 3 | 3 | 3 | 9 | limit_retest | — | $2,550,942 | $-320,160 | 7.97 |
| 23 | MNQ | limit_retest 4/2/1 | 4 | 2 | 1 | 7 | limit_retest | — | $134,406 | $-17,007 | 7.90 |
| 24 | ES | limit_retest 2/4/1 | 2 | 4 | 1 | 7 | limit_retest | — | $777,608 | $-100,658 | 7.73 |
| 25 | ES | limit_retest 2/2/4 | 2 | 2 | 4 | 8 | limit_retest | — | $926,262 | $-120,509 | 7.69 |
| 26 | YM | limit_retest 4/1/1 | 4 | 1 | 1 | 6 | limit_retest | — | $515,736 | $-67,525 | 7.64 |
| 27 | YM | limit_retest 5/2/1 | 5 | 2 | 1 | 8 | limit_retest | — | $697,234 | $-91,610 | 7.61 |
| 28 | YM | limit_retest 4/2/1 | 4 | 2 | 1 | 7 | limit_retest | — | $621,574 | $-81,932 | 7.59 |
| 29 | YM | limit_retest 2/1/1 | 2 | 1 | 1 | 4 | limit_retest | — | $364,416 | $-48,170 | 7.57 |
| 30 | YM | limit_retest 4/2/2 | 4 | 2 | 2 | 8 | limit_retest | — | $728,833 | $-96,340 | 7.57 |
| 31 | YM | limit_retest 3/2/1 | 3 | 2 | 1 | 6 | limit_retest | — | $545,915 | $-72,255 | 7.56 |
| 32 | YM | limit_retest 3/1/3 | 3 | 1 | 3 | 7 | limit_retest | — | $654,593 | $-86,662 | 7.55 |
| 33 | MNQ | limit_retest 2/1/1 | 2 | 1 | 1 | 4 | limit_retest | — | $81,470 | $-10,843 | 7.51 |
| 34 | MNQ | limit_retest 4/2/2 | 4 | 2 | 2 | 8 | limit_retest | — | $162,940 | $-21,686 | 7.51 |
| 35 | NQ | limit_retest 2/2/4 | 2 | 2 | 4 | 8 | limit_retest | — | $2,394,364 | $-320,160 | 7.48 |
| 36 | ES | limit_retest 1/1/3 | 1 | 1 | 3 | 5 | limit_retest | — | $597,534 | $-80,106 | 7.46 |
| 37 | MNQ | limit_retest 3/2/1 | 3 | 2 | 1 | 6 | limit_retest | — | $120,878 | $-16,264 | 7.43 |
| 38 | NQ | limit_retest 2/4/1 | 2 | 4 | 1 | 7 | limit_retest | — | $1,982,606 | $-266,800 | 7.43 |
| 39 | YM | limit_retest 1/1/1 (baseline) | 1 | 1 | 1 | 3 | limit_retest | — | $288,757 | $-39,810 | 7.25 |
| 40 | YM | limit_retest 2/2/2 | 2 | 2 | 2 | 6 | limit_retest | — | $577,514 | $-79,620 | 7.25 |
| 41 | YM | limit_retest 3/3/3 | 3 | 3 | 3 | 9 | limit_retest | — | $866,270 | $-119,430 | 7.25 |
| 42 | NQ | limit_retest 1/1/3 | 1 | 1 | 3 | 5 | limit_retest | — | $1,544,050 | $-213,440 | 7.23 |
| 43 | ES | limit_retest 1/2/4 | 1 | 2 | 4 | 7 | limit_retest | — | $859,215 | $-119,925 | 7.16 |
| 44 | MNQ | limit_retest 3/1/3 | 3 | 1 | 3 | 7 | limit_retest | — | $152,067 | $-21,338 | 7.13 |
| 45 | ES | limit_retest 1/3/3 | 1 | 3 | 3 | 7 | limit_retest | — | $852,090 | $-119,925 | 7.11 |
| 46 | NQ | limit_retest 1/2/4 | 1 | 2 | 4 | 7 | limit_retest | — | $2,205,341 | $-320,160 | 6.89 |
| 47 | YM | limit_retest 2/4/1 | 2 | 4 | 1 | 7 | limit_retest | — | $681,932 | $-99,525 | 6.85 |
| 48 | NQ | limit_retest 1/3/3 | 1 | 3 | 3 | 7 | limit_retest | — | $2,172,896 | $-320,160 | 6.79 |
| 49 | NQ | oco_stop 4/2/1 + 20% range-close | 4 | 2 | 1 | 7 | oco_stop | 20% | $1,426,707 | $-211,815 | 6.74 |
| 50 | YM | limit_retest 2/2/4 | 2 | 2 | 4 | 8 | limit_retest | — | $792,030 | $-119,430 | 6.63 |
| 51 | MNQ | limit_retest 1/1/1 (baseline) | 1 | 1 | 1 | 3 | limit_retest | — | $67,942 | $-10,669 | 6.37 |
| 52 | MNQ | limit_retest 2/2/2 | 2 | 2 | 2 | 6 | limit_retest | — | $135,884 | $-21,338 | 6.37 |
| 53 | MNQ | limit_retest 3/3/3 | 3 | 3 | 3 | 9 | limit_retest | — | $203,826 | $-32,007 | 6.37 |
| 54 | YM | limit_retest 1/1/3 | 1 | 1 | 3 | 5 | limit_retest | — | $503,274 | $-79,620 | 6.32 |
| 55 | MNQ | oco_stop 4/2/1 + 20% range-close | 4 | 2 | 1 | 7 | oco_stop | 20% | $128,978 | $-21,212 | 6.08 |
| 56 | MNQ | limit_retest 2/2/4 | 2 | 2 | 4 | 8 | limit_retest | — | $192,953 | $-32,007 | 6.03 |
| 57 | YM | limit_retest 1/2/4 | 1 | 2 | 4 | 7 | limit_retest | — | $716,371 | $-119,430 | 6.00 |
| 58 | YM | limit_retest 1/3/3 | 1 | 3 | 3 | 7 | limit_retest | — | $714,951 | $-119,430 | 5.99 |
| 59 | MNQ | limit_retest 2/4/1 | 2 | 4 | 1 | 7 | limit_retest | — | $159,109 | $-26,672 | 5.97 |
| 60 | MNQ | limit_retest 1/1/3 | 1 | 1 | 3 | 5 | limit_retest | — | $125,011 | $-21,338 | 5.86 |
| 61 | MYM | limit_retest 4/1/1 | 4 | 1 | 1 | 6 | limit_retest | — | $28,376 | $-4,977 | 5.70 |
| 62 | MNQ | limit_retest 1/2/4 | 1 | 2 | 4 | 7 | limit_retest | — | $179,425 | $-32,007 | 5.61 |
| 63 | MYM | limit_retest 5/2/1 | 5 | 2 | 1 | 8 | limit_retest | — | $38,278 | $-6,896 | 5.55 |
| 64 | MNQ | limit_retest 1/3/3 | 1 | 3 | 3 | 7 | limit_retest | — | $176,770 | $-32,007 | 5.52 |
| 65 | MYM | limit_retest 4/2/1 | 4 | 2 | 1 | 7 | limit_retest | — | $33,860 | $-6,327 | 5.35 |
| 66 | NQ | oco_stop 1/1/1 + 20% range-close | 1 | 1 | 1 | 3 | oco_stop | 20% | $741,289 | $-141,210 | 5.25 |
| 67 | MYM | limit_retest 3/2/1 | 3 | 2 | 1 | 6 | limit_retest | — | $29,442 | $-5,874 | 5.01 |
| 68 | MYM | limit_retest 2/1/1 | 2 | 1 | 1 | 4 | limit_retest | — | $19,540 | $-3,916 | 4.99 |
| 69 | MYM | limit_retest 4/2/2 | 4 | 2 | 2 | 8 | limit_retest | — | $39,081 | $-7,832 | 4.99 |
| 70 | MNQ | oco_stop 1/1/1 + 20% range-close | 1 | 1 | 1 | 3 | oco_stop | 20% | $66,845 | $-14,141 | 4.73 |
| 71 | NQ | limit_retest 4/2/1 + 20% range-close | 4 | 2 | 1 | 7 | limit_retest | 20% | $1,014,680 | $-214,660 | 4.73 |
| 72 | MYM | limit_retest 3/1/3 | 3 | 1 | 3 | 7 | limit_retest | — | $34,400 | $-7,832 | 4.39 |
| 73 | MNQ | limit_retest 4/2/1 + 20% range-close | 4 | 2 | 1 | 7 | limit_retest | 20% | $92,827 | $-21,486 | 4.32 |
| 74 | ES | oco_stop 1/1/1 + 20% range-close | 1 | 1 | 1 | 3 | oco_stop | 20% | $350,746 | $-86,332 | 4.06 |
| 75 | MYM | limit_retest 1/1/1 (baseline) | 1 | 1 | 1 | 3 | limit_retest | — | $15,123 | $-3,916 | 3.86 |
| 76 | MYM | limit_retest 2/2/2 | 2 | 2 | 2 | 6 | limit_retest | — | $30,246 | $-7,832 | 3.86 |
| 77 | MYM | limit_retest 3/3/3 | 3 | 3 | 3 | 9 | limit_retest | — | $45,368 | $-11,748 | 3.86 |
| 78 | MYM | limit_retest 2/4/1 | 2 | 4 | 1 | 7 | limit_retest | — | $35,992 | $-9,790 | 3.68 |
| 79 | YM | oco_stop 4/2/1 + 20% range-close | 4 | 2 | 1 | 7 | oco_stop | 20% | $415,290 | $-112,961 | 3.68 |
| 80 | NQ | limit_retest 1/1/1 + 20% range-close | 1 | 1 | 1 | 3 | limit_retest | 20% | $516,948 | $-141,210 | 3.66 |
| 81 | MYM | limit_retest 2/2/4 | 2 | 2 | 4 | 8 | limit_retest | — | $40,688 | $-11,748 | 3.46 |
| 82 | MNQ | limit_retest 1/1/1 + 20% range-close | 1 | 1 | 1 | 3 | limit_retest | 20% | $48,137 | $-14,141 | 3.40 |
| 83 | ES | oco_stop 4/2/1 + 20% range-close | 4 | 2 | 1 | 7 | oco_stop | 20% | $672,935 | $-199,017 | 3.38 |
| 84 | MYM | limit_retest 1/1/3 | 1 | 1 | 3 | 5 | limit_retest | — | $25,565 | $-7,832 | 3.26 |
| 85 | MYM | limit_retest 1/3/3 | 1 | 3 | 3 | 7 | limit_retest | — | $36,533 | $-11,748 | 3.11 |
| 86 | MYM | limit_retest 1/2/4 | 1 | 2 | 4 | 7 | limit_retest | — | $36,270 | $-11,748 | 3.09 |
| 87 | YM | oco_stop 1/1/1 + 20% range-close | 1 | 1 | 1 | 3 | oco_stop | 20% | $182,900 | $-63,598 | 2.88 |
| 88 | MYM | oco_stop 4/2/1 + 20% range-close | 4 | 2 | 1 | 7 | oco_stop | 20% | $29,578 | $-10,952 | 2.70 |
| 89 | YM | limit_retest 4/2/1 + 20% range-close | 4 | 2 | 1 | 7 | limit_retest | 20% | $282,238 | $-106,668 | 2.65 |
| 90 | YM | limit_retest 1/1/1 + 20% range-close | 1 | 1 | 1 | 3 | limit_retest | 20% | $128,034 | $-62,364 | 2.05 |
| 91 | MYM | oco_stop 1/1/1 + 20% range-close | 1 | 1 | 1 | 3 | oco_stop | 20% | $12,098 | $-6,098 | 1.98 |
| 92 | MYM | limit_retest 4/2/1 + 20% range-close | 4 | 2 | 1 | 7 | limit_retest | 20% | $19,370 | $-10,655 | 1.82 |
| 93 | ES | limit_retest 4/2/1 + 20% range-close | 4 | 2 | 1 | 7 | limit_retest | 20% | $208,328 | $-121,132 | 1.72 |
| 94 | ES | limit_retest 1/1/1 + 20% range-close | 1 | 1 | 1 | 3 | limit_retest | 20% | $92,037 | $-64,766 | 1.42 |
| 95 | MYM | limit_retest 1/1/1 + 20% range-close | 1 | 1 | 1 | 3 | limit_retest | 20% | $7,597 | $-6,237 | 1.22 |
| 96 | MES | oco_stop 1/1/1 + 20% range-close | 1 | 1 | 1 | 3 | oco_stop | 20% | $9,878 | $-8,546 | 1.16 |
| 97 | MES | oco_stop 4/2/1 + 20% range-close | 4 | 2 | 1 | 7 | oco_stop | 20% | $18,358 | $-19,940 | 0.92 |
| 98 | MES | limit_retest 2/2/4 | 2 | 2 | 4 | 8 | limit_retest | — | $5,341 | $-7,702 | 0.69 |
| 99 | MES | limit_retest 2/4/1 | 2 | 4 | 1 | 7 | limit_retest | — | $4,625 | $-6,671 | 0.69 |
| 100 | MES | limit_retest 3/3/3 | 3 | 3 | 3 | 9 | limit_retest | — | $5,864 | $-8,577 | 0.68 |
| 101 | MES | limit_retest 1/1/1 (baseline) | 1 | 1 | 1 | 3 | limit_retest | — | $1,955 | $-2,859 | 0.68 |
| 102 | MES | limit_retest 2/2/2 | 2 | 2 | 2 | 6 | limit_retest | — | $3,910 | $-5,718 | 0.68 |
| 103 | MES | limit_retest 3/1/3 | 3 | 1 | 3 | 7 | limit_retest | — | $4,433 | $-6,671 | 0.66 |
| 104 | MES | limit_retest 1/1/3 | 1 | 1 | 3 | 5 | limit_retest | — | $3,386 | $-5,135 | 0.66 |
| 105 | MES | limit_retest 4/2/2 | 4 | 2 | 2 | 8 | limit_retest | — | $4,956 | $-7,624 | 0.65 |
| 106 | MES | limit_retest 2/1/1 | 2 | 1 | 1 | 4 | limit_retest | — | $2,478 | $-3,812 | 0.65 |
| 107 | MES | limit_retest 3/2/1 | 3 | 2 | 1 | 6 | limit_retest | — | $3,717 | $-5,718 | 0.65 |
| 108 | MES | limit_retest 4/2/1 | 4 | 2 | 1 | 7 | limit_retest | — | $4,240 | $-6,671 | 0.64 |
| 109 | MES | limit_retest 1/2/4 | 1 | 2 | 4 | 7 | limit_retest | — | $4,818 | $-7,702 | 0.63 |
| 110 | MES | limit_retest 1/3/3 | 1 | 3 | 3 | 7 | limit_retest | — | $4,818 | $-7,702 | 0.63 |
| 111 | MES | limit_retest 5/2/1 | 5 | 2 | 1 | 8 | limit_retest | — | $4,764 | $-7,624 | 0.62 |
| 112 | MES | limit_retest 4/1/1 | 4 | 1 | 1 | 6 | limit_retest | — | $3,524 | $-5,718 | 0.62 |
| 113 | MES | limit_retest 4/2/1 + 20% range-close | 4 | 2 | 1 | 7 | limit_retest | 20% | $5,478 | $-12,176 | 0.45 |
| 114 | MES | limit_retest 1/1/1 + 20% range-close | 1 | 1 | 1 | 3 | limit_retest | 20% | $2,009 | $-6,542 | 0.31 |