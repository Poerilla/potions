# Yearly ORB FX/metals exit-variant PnL attribution

Hub: `/home/tester/hsm/potions/live/state/yearly_orb_exit_variants_fx_metals`

Source: audit `unit_fills.csv` (points × point_value − fee/unit; AUDJPY ÷110).
Exit buckets map fill `exit_reason` (broker `close` → mid/range flatten by `exit_mode`).

## Books covered

| Instrument | Slug | Exit | Size | Summary N/S | Attributed net |
|---|---|---|---:|---:|---:|
| AUDJPY | `L_4_1_1_mid` | mid_close | 4/1/1 | -0.02 | $-2,778 |
| AUDJPY | `L_5_2_1_mid` | mid_close | 5/2/1 | -0.07 | $-13,020 |
| AUDJPY | `L_4_2_1_mid` | mid_close | 4/2/1 | -0.14 | $-24,157 |
| AUDJPY | `L_1_1_1_mid` | mid_close | 1/1/1 | -0.30 | $-36,191 |
| AUDJPY | `L_4_2_1_swing` | inside_swing_take | 4/2/1 | -0.44 | $-127,133 |
| AUDJPY | `L_1_1_1_swing` | inside_swing_take | 1/1/1 | -0.46 | $-73,024 |
| AUDJPY | `L_4_2_1` | range_close | 4/2/1 | -0.58 | $-146,581 |
| AUDJPY | `L_1_1_1` | range_close | 1/1/1 | -0.76 | $-93,825 |
| XAGUSD | `L_4_2_1` | range_close | 4/2/1 | 1.29 | $65,540 |
| XAGUSD | `L_1_1_3_swing` | inside_swing_take | 1/1/3 | 1.25 | $120,925 |
| XAGUSD | `L_1_2_4_swing` | inside_swing_take | 1/2/4 | 1.22 | $168,632 |
| XAGUSD | `L_1_1_1_swing` | inside_swing_take | 1/1/1 | 1.10 | $50,042 |
| XAGUSD | `L_4_2_1_swing` | inside_swing_take | 4/2/1 | 0.94 | $69,312 |
| XAGUSD | `L_1_1_1_mid` | mid_close | 1/1/1 | 0.88 | $44,440 |
| XAGUSD | `L_1_1_1` | range_close | 1/1/1 | 0.66 | $23,155 |
| XAGUSD | `L_4_2_1_mid` | mid_close | 4/2/1 | 0.63 | $56,314 |
| XAUUSD | `L_1_3_3_mid` | mid_close | 1/3/3 | 4.58 | $997,267 |
| XAUUSD | `L_1_2_4_mid` | mid_close | 1/2/4 | 4.33 | $1,088,525 |
| XAUUSD | `L_1_1_1_mid` | mid_close | 1/1/1 | 4.31 | $360,690 |
| XAUUSD | `L_4_2_1_mid` | mid_close | 4/2/1 | 3.68 | $601,410 |
| XAUUSD | `L_1_1_1_swing` | inside_swing_take | 1/1/1 | 3.23 | $289,860 |
| XAUUSD | `L_4_2_1_swing` | inside_swing_take | 4/2/1 | 3.20 | $470,997 |
| XAUUSD | `L_1_1_1` | range_close | 1/1/1 | 1.99 | $216,047 |
| XAUUSD | `L_4_2_1` | range_close | 4/2/1 | 1.86 | $310,855 |

## Exit-mode compare (same sizing)

### L_1_1_1 family

| Instrument | Mode | Net | Targets | Stops | Runner stops | Mid/range flatten | Forced/year |
|---|---|---:|---:|---:|---:|---:|---:|
| AUDJPY | mid_close | $-36,191 | $90,643 | $-106,451 | $-68,174 | $47,791 | $0 |
| AUDJPY | inside_swing_take | $-73,024 | $95,040 | $-149,960 | $-87,366 | $0 | $69,262 |
| AUDJPY | range_close | $-93,825 | $53,590 | $-12,025 | $-6,759 | $-128,632 | $0 |
| XAGUSD | inside_swing_take | $50,042 | $71,789 | $-60,974 | $-36,413 | $0 | $75,640 |
| XAGUSD | mid_close | $44,440 | $71,789 | $-58,468 | $-35,422 | $66,540 | $0 |
| XAGUSD | range_close | $23,155 | $55,963 | $-2,736 | $-1,423 | $-28,650 | $0 |
| XAUUSD | mid_close | $360,690 | $279,284 | $-138,914 | $-86,169 | $306,489 | $0 |
| XAUUSD | inside_swing_take | $289,860 | $256,448 | $-153,212 | $-90,036 | $0 | $276,661 |
| XAUUSD | range_close | $216,047 | $177,102 | $-25,328 | $-12,664 | $76,936 | $0 |

### L_4_2_1 family

| Instrument | Mode | Net | Targets | Stops | Runner stops | Mid/range flatten | Forced/year |
|---|---|---:|---:|---:|---:|---:|---:|
| AUDJPY | mid_close | $-24,157 | $279,345 | $-289,459 | $-68,174 | $54,131 | $0 |
| AUDJPY | inside_swing_take | $-127,133 | $296,932 | $-425,111 | $-87,366 | $0 | $88,412 |
| AUDJPY | range_close | $-146,581 | $193,672 | $-34,583 | $-6,759 | $-298,912 | $0 |
| XAGUSD | range_close | $65,540 | $162,151 | $-8,101 | $-1,423 | $-87,088 | $0 |
| XAGUSD | inside_swing_take | $69,312 | $197,721 | $-171,080 | $-36,413 | $0 | $79,084 |
| XAGUSD | mid_close | $56,314 | $197,721 | $-163,036 | $-35,422 | $57,050 | $0 |
| XAUUSD | mid_close | $601,410 | $756,319 | $-383,325 | $-86,169 | $314,585 | $0 |
| XAUUSD | inside_swing_take | $470,997 | $693,311 | $-432,783 | $-90,036 | $0 | $300,505 |
| XAUUSD | range_close | $310,855 | $501,951 | $-75,983 | $-12,664 | $-102,450 | $0 |

## AUDJPY — `L_4_1_1_mid` (mid_close)

Sizing 4/1/1 · summary N/S **-0.02** · attributed $-2,778 (n_units=306).

### By exit bucket

| Bucket | N | Net | Win$ | Loss$ | Share |
|---|---:|---:|---:|---:|---:|
| `target` | 109 | $237,731 | $237,731 | $0 | -8559% |
| `stop` | 123 | $-221,287 | $0 | $-221,287 | 7967% |
| `runner_stop` | 37 | $-68,174 | $0 | $-68,174 | 2454% |
| `mid_close_flatten` | 37 | $48,952 | $90,880 | $-41,928 | -1762% |

### By unit role (entry_reason)

| Role | N | Net | Share |
|---|---:|---:|---:|
| `scaleout_or_tp` | 255 | $-21,688 | 781% |
| `runner` | 51 | $18,910 | -681% |

### By direction

- **Short**: $-72,318 (n=120)
- **Long**: $69,540 (n=186)

### Year extremes

- Best: **2009** $47,653 (n=6)
- Worst: **2025** $-24,973 (n=16)

## AUDJPY — `L_5_2_1_mid` (mid_close)

Sizing 5/2/1 · summary N/S **-0.07** · attributed $-13,020 (n_units=408).

### By exit bucket

| Bucket | N | Net | Win$ | Loss$ | Share |
|---|---:|---:|---:|---:|---:|
| `target` | 140 | $328,375 | $328,375 | $0 | -2522% |
| `stop` | 180 | $-327,738 | $0 | $-327,738 | 2517% |
| `runner_stop` | 37 | $-68,174 | $0 | $-68,174 | 524% |
| `mid_close_flatten` | 51 | $54,518 | $113,585 | $-59,067 | -419% |

### By unit role (entry_reason)

| Role | N | Net | Share |
|---|---:|---:|---:|
| `scaleout_or_tp` | 357 | $-8,593 | 66% |
| `runner` | 51 | $-4,427 | 34% |

### By direction

- **Short**: $-109,622 (n=160)
- **Long**: $96,602 (n=248)

### Year extremes

- Best: **2009** $63,647 (n=8)
- Worst: **2025** $-33,854 (n=21)

## AUDJPY — `L_4_2_1_mid` (mid_close)

Sizing 4/2/1 · summary N/S **-0.14** · attributed $-24,157 (n_units=357).

### By exit bucket

| Bucket | N | Net | Win$ | Loss$ | Share |
|---|---:|---:|---:|---:|---:|
| `stop` | 158 | $-289,459 | $0 | $-289,459 | 1198% |
| `target` | 114 | $279,345 | $279,345 | $0 | -1156% |
| `runner_stop` | 37 | $-68,174 | $0 | $-68,174 | 282% |
| `mid_close_flatten` | 48 | $54,131 | $109,373 | $-55,243 | -224% |

### By unit role (entry_reason)

| Role | N | Net | Share |
|---|---:|---:|---:|
| `scaleout_or_tp` | 306 | $-29,923 | 124% |
| `runner` | 51 | $5,766 | -24% |

### By direction

- **Short**: $-105,352 (n=140)
- **Long**: $81,194 (n=217)

### Year extremes

- Best: **2009** $60,449 (n=7)
- Worst: **2011** $-32,490 (n=21)

## AUDJPY — `L_1_1_1_mid` (mid_close)

Sizing 1/1/1 · summary N/S **-0.30** · attributed $-36,191 (n_units=153).

### By exit bucket

| Bucket | N | Net | Win$ | Loss$ | Share |
|---|---:|---:|---:|---:|---:|
| `stop` | 57 | $-106,451 | $0 | $-106,451 | 294% |
| `target` | 31 | $90,643 | $90,643 | $0 | -250% |
| `runner_stop` | 37 | $-68,174 | $0 | $-68,174 | 188% |
| `mid_close_flatten` | 28 | $47,791 | $78,245 | $-30,454 | -132% |

### By unit role (entry_reason)

| Role | N | Net | Share |
|---|---:|---:|---:|
| `runner` | 51 | $-26,982 | 75% |
| `scaleout_or_tp` | 102 | $-9,208 | 25% |

### By direction

- **Short**: $-59,507 (n=60)
- **Long**: $23,317 (n=93)

### Year extremes

- Best: **2009** $38,057 (n=3)
- Worst: **2011** $-22,626 (n=9)

## AUDJPY — `L_4_2_1_swing` (inside_swing_take)

Sizing 4/2/1 · summary N/S **-0.44** · attributed $-127,133 (n_units=539).

### By exit bucket

| Bucket | N | Net | Win$ | Loss$ | Share |
|---|---:|---:|---:|---:|---:|
| `stop` | 320 | $-425,111 | $0 | $-425,111 | 334% |
| `target` | 126 | $296,932 | $296,932 | $0 | -234% |
| `forced_close` | 25 | $88,412 | $88,412 | $0 | -70% |
| `runner_stop` | 68 | $-87,366 | $0 | $-87,366 | 69% |

### By unit role (entry_reason)

| Role | N | Net | Share |
|---|---:|---:|---:|
| `scaleout_or_tp` | 462 | $-109,943 | 86% |
| `runner` | 77 | $-17,191 | 14% |

### By direction

- **Short**: $-130,866 (n=203)
- **Long**: $3,732 (n=336)

### Year extremes

- Best: **2009** $60,449 (n=7)
- Worst: **2010** $-57,150 (n=43)

## AUDJPY — `L_1_1_1_swing` (inside_swing_take)

Sizing 1/1/1 · summary N/S **-0.46** · attributed $-73,024 (n_units=231).

### By exit bucket

| Bucket | N | Net | Win$ | Loss$ | Share |
|---|---:|---:|---:|---:|---:|
| `stop` | 113 | $-149,960 | $0 | $-149,960 | 205% |
| `target` | 34 | $95,040 | $95,040 | $0 | -130% |
| `runner_stop` | 68 | $-87,366 | $0 | $-87,366 | 120% |
| `forced_close` | 16 | $69,262 | $69,262 | $0 | -95% |

### By unit role (entry_reason)

| Role | N | Net | Share |
|---|---:|---:|---:|
| `scaleout_or_tp` | 154 | $-44,261 | 61% |
| `runner` | 77 | $-28,763 | 39% |

### By direction

- **Short**: $-63,235 (n=87)
- **Long**: $-9,789 (n=144)

### Year extremes

- Best: **2009** $38,057 (n=3)
- Worst: **2022** $-20,708 (n=21)

## AUDJPY — `L_4_2_1` (range_close)

Sizing 4/2/1 · summary N/S **-0.58** · attributed $-146,581 (n_units=1022).

### By exit bucket

| Bucket | N | Net | Win$ | Loss$ | Share |
|---|---:|---:|---:|---:|---:|
| `range_close_flatten` | 858 | $-298,912 | $42,538 | $-341,450 | 204% |
| `target` | 108 | $193,672 | $193,672 | $0 | -132% |
| `stop` | 46 | $-34,583 | $0 | $-34,583 | 24% |
| `runner_stop` | 10 | $-6,759 | $0 | $-6,759 | 5% |

### By unit role (entry_reason)

| Role | N | Net | Share |
|---|---:|---:|---:|
| `scaleout_or_tp` | 876 | $-128,222 | 87% |
| `runner` | 146 | $-18,359 | 13% |

### By direction

- **Short**: $-103,590 (n=392)
- **Long**: $-42,991 (n=630)

### Year extremes

- Best: **2005** $23,784 (n=20)
- Worst: **2010** $-57,771 (n=77)

## AUDJPY — `L_1_1_1` (range_close)

Sizing 1/1/1 · summary N/S **-0.76** · attributed $-93,825 (n_units=438).

### By exit bucket

| Bucket | N | Net | Win$ | Loss$ | Share |
|---|---:|---:|---:|---:|---:|
| `range_close_flatten` | 384 | $-128,632 | $25,687 | $-154,319 | 137% |
| `target` | 28 | $53,590 | $53,590 | $0 | -57% |
| `stop` | 16 | $-12,025 | $0 | $-12,025 | 13% |
| `runner_stop` | 10 | $-6,759 | $0 | $-6,759 | 7% |

### By unit role (entry_reason)

| Role | N | Net | Share |
|---|---:|---:|---:|
| `scaleout_or_tp` | 292 | $-69,851 | 74% |
| `runner` | 146 | $-23,974 | 26% |

### By direction

- **Short**: $-56,903 (n=168)
- **Long**: $-36,922 (n=270)

### Year extremes

- Best: **2026** $10,000 (n=2)
- Worst: **2010** $-26,893 (n=33)

## XAGUSD — `L_4_2_1` (range_close)

Sizing 4/2/1 · summary N/S **1.29** · attributed $65,540 (n_units=623).

### By exit bucket

| Bucket | N | Net | Win$ | Loss$ | Share |
|---|---:|---:|---:|---:|---:|
| `target` | 112 | $162,151 | $162,151 | $0 | 247% |
| `range_close_flatten` | 479 | $-87,088 | $23,579 | $-110,666 | -133% |
| `stop` | 26 | $-8,101 | $0 | $-8,101 | -12% |
| `runner_stop` | 6 | $-1,423 | $0 | $-1,423 | -2% |

### By unit role (entry_reason)

| Role | N | Net | Share |
|---|---:|---:|---:|
| `scaleout_or_tp` | 534 | $70,867 | 108% |
| `runner` | 89 | $-5,327 | -8% |

### By direction

- **Long**: $100,992 (n=301)
- **Short**: $-35,453 (n=322)

### Year extremes

- Best: **2011** $23,158 (n=29)
- Worst: **2012** $-15,806 (n=56)

## XAGUSD — `L_1_1_3_swing` (inside_swing_take)

Sizing 1/1/3 · summary N/S **1.25** · attributed $120,925 (n_units=255).

### By exit bucket

| Bucket | N | Net | Win$ | Loss$ | Share |
|---|---:|---:|---:|---:|---:|
| `forced_close` | 37 | $219,348 | $220,201 | $-852 | 181% |
| `runner_stop` | 120 | $-109,239 | $0 | $-109,239 | -90% |
| `target` | 34 | $71,789 | $71,789 | $0 | 59% |
| `stop` | 64 | $-60,974 | $0 | $-60,974 | -50% |

### By unit role (entry_reason)

| Role | N | Net | Share |
|---|---:|---:|---:|
| `runner` | 153 | $124,460 | 103% |
| `scaleout_or_tp` | 102 | $-3,535 | -3% |

### By direction

- **Long**: $136,360 (n=140)
- **Short**: $-15,435 (n=115)

### Year extremes

- Best: **2026** $114,194 (n=3)
- Worst: **2023** $-15,690 (n=20)

## XAGUSD — `L_1_2_4_swing` (inside_swing_take)

Sizing 1/2/4 · summary N/S **1.22** · attributed $168,632 (n_units=357).

### By exit bucket

| Bucket | N | Net | Win$ | Loss$ | Share |
|---|---:|---:|---:|---:|---:|
| `forced_close` | 51 | $295,158 | $296,352 | $-1,194 | 175% |
| `runner_stop` | 160 | $-145,652 | $0 | $-145,652 | -86% |
| `target` | 44 | $116,507 | $116,507 | $0 | 69% |
| `stop` | 102 | $-97,382 | $0 | $-97,382 | -58% |

### By unit role (entry_reason)

| Role | N | Net | Share |
|---|---:|---:|---:|
| `scaleout_or_tp` | 153 | $110,566 | 66% |
| `runner` | 204 | $58,066 | 34% |

### By direction

- **Long**: $191,728 (n=196)
- **Short**: $-23,097 (n=161)

### Year extremes

- Best: **2026** $152,258 (n=4)
- Worst: **2023** $-23,704 (n=28)

## XAGUSD — `L_1_1_1_swing` (inside_swing_take)

Sizing 1/1/1 · summary N/S **1.10** · attributed $50,042 (n_units=153).

### By exit bucket

| Bucket | N | Net | Win$ | Loss$ | Share |
|---|---:|---:|---:|---:|---:|
| `forced_close` | 15 | $75,640 | $76,151 | $-512 | 151% |
| `target` | 34 | $71,789 | $71,789 | $0 | 143% |
| `stop` | 64 | $-60,974 | $0 | $-60,974 | -122% |
| `runner_stop` | 40 | $-36,413 | $0 | $-36,413 | -73% |

### By unit role (entry_reason)

| Role | N | Net | Share |
|---|---:|---:|---:|
| `scaleout_or_tp` | 102 | $55,254 | 110% |
| `runner` | 51 | $-5,212 | -10% |

### By direction

- **Long**: $60,782 (n=84)
- **Short**: $-10,740 (n=69)

### Year extremes

- Best: **2026** $38,064 (n=1)
- Worst: **2023** $-7,676 (n=12)

## XAGUSD — `L_4_2_1_swing` (inside_swing_take)

Sizing 4/2/1 · summary N/S **0.94** · attributed $69,312 (n_units=357).

### By exit bucket

| Bucket | N | Net | Win$ | Loss$ | Share |
|---|---:|---:|---:|---:|---:|
| `target` | 116 | $197,721 | $197,721 | $0 | 285% |
| `stop` | 180 | $-171,080 | $0 | $-171,080 | -247% |
| `forced_close` | 21 | $79,084 | $80,277 | $-1,194 | 114% |
| `runner_stop` | 40 | $-36,413 | $0 | $-36,413 | -53% |

### By unit role (entry_reason)

| Role | N | Net | Share |
|---|---:|---:|---:|
| `scaleout_or_tp` | 306 | $57,004 | 82% |
| `runner` | 51 | $12,307 | 18% |

### By direction

- **Long**: $94,599 (n=196)
- **Short**: $-25,288 (n=161)

### Year extremes

- Best: **2026** $38,064 (n=1)
- Worst: **2004** $-13,090 (n=28)

## XAGUSD — `L_1_1_1_mid` (mid_close)

Sizing 1/1/1 · summary N/S **0.88** · attributed $44,440 (n_units=141).

### By exit bucket

| Bucket | N | Net | Win$ | Loss$ | Share |
|---|---:|---:|---:|---:|---:|
| `target` | 34 | $71,789 | $71,789 | $0 | 162% |
| `mid_close_flatten` | 20 | $66,540 | $77,112 | $-10,572 | 150% |
| `stop` | 53 | $-58,468 | $0 | $-58,468 | -132% |
| `runner_stop` | 34 | $-35,422 | $0 | $-35,422 | -80% |

### By unit role (entry_reason)

| Role | N | Net | Share |
|---|---:|---:|---:|
| `runner` | 47 | $37,884 | 85% |
| `scaleout_or_tp` | 94 | $6,556 | 15% |

### By direction

- **Long**: $50,834 (n=84)
- **Short**: $-6,395 (n=57)

### Year extremes

- Best: **2026** $38,064 (n=1)
- Worst: **2023** $-9,420 (n=12)

## XAGUSD — `L_1_1_1` (range_close)

Sizing 1/1/1 · summary N/S **0.66** · attributed $23,155 (n_units=267).

### By exit bucket

| Bucket | N | Net | Win$ | Loss$ | Share |
|---|---:|---:|---:|---:|---:|
| `target` | 31 | $55,963 | $55,963 | $0 | 242% |
| `range_close_flatten` | 221 | $-28,650 | $22,149 | $-50,798 | -124% |
| `stop` | 9 | $-2,736 | $0 | $-2,736 | -12% |
| `runner_stop` | 6 | $-1,423 | $0 | $-1,423 | -6% |

### By unit role (entry_reason)

| Role | N | Net | Share |
|---|---:|---:|---:|
| `runner` | 89 | $20,586 | 89% |
| `scaleout_or_tp` | 178 | $2,570 | 11% |

### By direction

- **Long**: $41,813 (n=129)
- **Short**: $-18,658 (n=138)

### Year extremes

- Best: **2011** $10,656 (n=13)
- Worst: **2012** $-6,774 (n=24)

## XAGUSD — `L_4_2_1_mid` (mid_close)

Sizing 4/2/1 · summary N/S **0.63** · attributed $56,314 (n_units=329).

### By exit bucket

| Bucket | N | Net | Win$ | Loss$ | Share |
|---|---:|---:|---:|---:|---:|
| `target` | 116 | $197,721 | $197,721 | $0 | 351% |
| `stop` | 148 | $-163,036 | $0 | $-163,036 | -290% |
| `mid_close_flatten` | 31 | $57,050 | $81,718 | $-24,668 | 101% |
| `runner_stop` | 34 | $-35,422 | $0 | $-35,422 | -63% |

### By unit role (entry_reason)

| Role | N | Net | Share |
|---|---:|---:|---:|
| `scaleout_or_tp` | 282 | $53,429 | 95% |
| `runner` | 47 | $2,885 | 5% |

### By direction

- **Long**: $72,966 (n=196)
- **Short**: $-16,652 (n=133)

### Year extremes

- Best: **2026** $38,064 (n=1)
- Worst: **2011** $-17,922 (n=29)

## XAUUSD — `L_1_3_3_mid` (mid_close)

Sizing 1/3/3 · summary N/S **4.58** · attributed $997,267 (n_units=280).

### By exit bucket

| Bucket | N | Net | Win$ | Loss$ | Share |
|---|---:|---:|---:|---:|---:|
| `mid_close_flatten` | 71 | $926,917 | $963,909 | $-36,992 | 93% |
| `target` | 54 | $640,103 | $640,103 | $0 | 64% |
| `stop` | 83 | $-311,247 | $0 | $-311,247 | -31% |
| `runner_stop` | 72 | $-258,506 | $0 | $-258,506 | -26% |

### By unit role (entry_reason)

| Role | N | Net | Share |
|---|---:|---:|---:|
| `scaleout_or_tp` | 160 | $665,275 | 67% |
| `runner` | 120 | $331,992 | 33% |

### By direction

- **Long**: $1,101,537 (n=161)
- **Short**: $-104,270 (n=119)

### Year extremes

- Best: **2026** $365,984 (n=3)
- Worst: **2008** $-106,887 (n=14)

## XAUUSD — `L_1_2_4_mid` (mid_close)

Sizing 1/2/4 · summary N/S **4.33** · attributed $1,088,525 (n_units=280).

### By exit bucket

| Bucket | N | Net | Win$ | Loss$ | Share |
|---|---:|---:|---:|---:|---:|
| `mid_close_flatten` | 80 | $1,198,587 | $1,235,579 | $-36,992 | 110% |
| `target` | 44 | $459,694 | $459,694 | $0 | 42% |
| `runner_stop` | 96 | $-344,675 | $0 | $-344,675 | -32% |
| `stop` | 60 | $-225,081 | $0 | $-225,081 | -21% |

### By unit role (entry_reason)

| Role | N | Net | Share |
|---|---:|---:|---:|
| `runner` | 160 | $766,117 | 70% |
| `scaleout_or_tp` | 120 | $322,408 | 30% |

### By direction

- **Long**: $1,176,330 (n=161)
- **Short**: $-87,805 (n=119)

### Year extremes

- Best: **2026** $487,979 (n=4)
- Worst: **2008** $-106,887 (n=14)

## XAUUSD — `L_1_1_1_mid` (mid_close)

Sizing 1/1/1 · summary N/S **4.31** · attributed $360,690 (n_units=120).

### By exit bucket

| Bucket | N | Net | Win$ | Loss$ | Share |
|---|---:|---:|---:|---:|---:|
| `mid_close_flatten` | 25 | $306,489 | $322,343 | $-15,854 | 85% |
| `target` | 34 | $279,284 | $279,284 | $0 | 77% |
| `stop` | 37 | $-138,914 | $0 | $-138,914 | -39% |
| `runner_stop` | 24 | $-86,169 | $0 | $-86,169 | -24% |

### By unit role (entry_reason)

| Role | N | Net | Share |
|---|---:|---:|---:|
| `scaleout_or_tp` | 80 | $242,103 | 67% |
| `runner` | 40 | $118,587 | 33% |

### By direction

- **Long**: $397,689 (n=69)
- **Short**: $-36,999 (n=51)

### Year extremes

- Best: **2026** $121,995 (n=1)
- Worst: **2008** $-38,282 (n=6)

## XAUUSD — `L_4_2_1_mid` (mid_close)

Sizing 4/2/1 · summary N/S **3.68** · attributed $601,410 (n_units=280).

### By exit bucket

| Bucket | N | Net | Win$ | Loss$ | Share |
|---|---:|---:|---:|---:|---:|
| `target` | 116 | $756,319 | $756,319 | $0 | 126% |
| `stop` | 102 | $-383,325 | $0 | $-383,325 | -64% |
| `mid_close_flatten` | 38 | $314,585 | $351,577 | $-36,992 | 52% |
| `runner_stop` | 24 | $-86,169 | $0 | $-86,169 | -14% |

### By unit role (entry_reason)

| Role | N | Net | Share |
|---|---:|---:|---:|
| `scaleout_or_tp` | 240 | $399,693 | 66% |
| `runner` | 40 | $201,717 | 34% |

### By direction

- **Long**: $673,552 (n=161)
- **Short**: $-72,142 (n=119)

### Year extremes

- Best: **2025** $155,710 (n=14)
- Worst: **2012** $-79,205 (n=15)

## XAUUSD — `L_1_1_1_swing` (inside_swing_take)

Sizing 1/1/1 · summary N/S **3.23** · attributed $289,860 (n_units=144).

### By exit bucket

| Bucket | N | Net | Win$ | Loss$ | Share |
|---|---:|---:|---:|---:|---:|
| `forced_close` | 19 | $276,661 | $276,661 | $0 | 95% |
| `target` | 31 | $256,448 | $256,448 | $0 | 88% |
| `stop` | 59 | $-153,212 | $0 | $-153,212 | -53% |
| `runner_stop` | 35 | $-90,036 | $0 | $-90,036 | -31% |

### By unit role (entry_reason)

| Role | N | Net | Share |
|---|---:|---:|---:|
| `scaleout_or_tp` | 96 | $173,922 | 60% |
| `runner` | 48 | $115,938 | 40% |

### By direction

- **Long**: $376,170 (n=78)
- **Short**: $-86,310 (n=66)

### Year extremes

- Best: **2026** $121,995 (n=1)
- Worst: **2008** $-41,723 (n=9)

## XAUUSD — `L_4_2_1_swing` (inside_swing_take)

Sizing 4/2/1 · summary N/S **3.20** · attributed $470,997 (n_units=336).

### By exit bucket

| Bucket | N | Net | Win$ | Loss$ | Share |
|---|---:|---:|---:|---:|---:|
| `target` | 106 | $693,311 | $693,311 | $0 | 147% |
| `stop` | 168 | $-432,783 | $0 | $-432,783 | -92% |
| `forced_close` | 27 | $300,505 | $300,505 | $0 | 64% |
| `runner_stop` | 35 | $-90,036 | $0 | $-90,036 | -19% |

### By unit role (entry_reason)

| Role | N | Net | Share |
|---|---:|---:|---:|
| `scaleout_or_tp` | 288 | $440,928 | 94% |
| `runner` | 48 | $30,069 | 6% |

### By direction

- **Long**: $616,658 (n=182)
- **Short**: $-145,662 (n=154)

### Year extremes

- Best: **2025** $155,710 (n=14)
- Worst: **2008** $-76,370 (n=21)

## XAUUSD — `L_1_1_1` (range_close)

Sizing 1/1/1 · summary N/S **1.99** · attributed $216,047 (n_units=273).

### By exit bucket

| Bucket | N | Net | Win$ | Loss$ | Share |
|---|---:|---:|---:|---:|---:|
| `target` | 21 | $177,102 | $177,102 | $0 | 82% |
| `range_close_flatten` | 237 | $76,936 | $237,608 | $-160,672 | 36% |
| `stop` | 10 | $-25,328 | $0 | $-25,328 | -12% |
| `runner_stop` | 5 | $-12,664 | $0 | $-12,664 | -6% |

### By unit role (entry_reason)

| Role | N | Net | Share |
|---|---:|---:|---:|
| `scaleout_or_tp` | 182 | $198,714 | 92% |
| `runner` | 91 | $17,333 | 8% |

### By direction

- **Long**: $246,213 (n=150)
- **Short**: $-30,166 (n=123)

### Year extremes

- Best: **2026** $121,995 (n=1)
- Worst: **2020** $-27,474 (n=21)

## XAUUSD — `L_4_2_1` (range_close)

Sizing 4/2/1 · summary N/S **1.86** · attributed $310,855 (n_units=637).

### By exit bucket

| Bucket | N | Net | Win$ | Loss$ | Share |
|---|---:|---:|---:|---:|---:|
| `target` | 76 | $501,951 | $501,951 | $0 | 161% |
| `range_close_flatten` | 526 | $-102,450 | $261,538 | $-363,988 | -33% |
| `stop` | 30 | $-75,983 | $0 | $-75,983 | -24% |
| `runner_stop` | 5 | $-12,664 | $0 | $-12,664 | -4% |

### By unit role (entry_reason)

| Role | N | Net | Share |
|---|---:|---:|---:|
| `scaleout_or_tp` | 546 | $258,936 | 83% |
| `runner` | 91 | $51,918 | 17% |

### By direction

- **Long**: $334,566 (n=350)
- **Short**: $-23,711 (n=287)

### Year extremes

- Best: **2025** $155,710 (n=14)
- Worst: **2020** $-64,107 (n=49)

## Stance

- Research / not promotion-safe.
- Prefer books where **targets** (not flatten scratches) dominate net.
- If mid_close N/S lift is mostly fewer stop scrapes vs true target alpha, sizing should favor TP/runner weight only after yearly robustness.
- Next: deep-check + win/loss charts on metals mid/swing leaders; sit out AUDJPY until exit mix flips.
