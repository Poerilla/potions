# Structure VWAP scale-in (NQ RTH)

Split VWAP entries inside the active structure; SL at structure bottom/top; re-arm only after a 15m close back inside after a stop-out. **5×3ct** slices (full 15 only if filled). Ladder from avg: 5@+25→±12, 5@+50, 5@+200; fav ST→BE.

## Results

| metric | value |
|---|---|
| trades | 13898 |
| net $ | -6438922 |
| win% | 2.9 |
| PF | 0.171 |
| avg $/trade | -463.3 |
| avg slices | 1.14 |
| pct full size (15) | 0.9 |
| long / short | 6599 / 7299 |

### By exit reason

| exit_reason                      |   count |               sum |      mean |
|:---------------------------------|--------:|------------------:|----------:|
| eod                              |      80 |   14071.9         |   175.899 |
| scale_25+eod                     |      18 |   83284           |  4626.89  |
| scale_25+scale_50+eod            |      35 |  501379           | 14325.1   |
| scale_25+scale_50+runner_200     |       1 |   15464           | 15464     |
| scale_25+scale_50+st_flip        |       7 |   48198           |  6885.42  |
| scale_25+scale_50+structure_stop |      13 |   95846.9         |  7372.83  |
| scale_25+st_flip                 |     122 |  228845           |  1875.78  |
| scale_25+structure_stop          |     154 |  286403           |  1859.76  |
| scale_25+tight_stop              |       7 |   15694           |  2242     |
| st_flip                          |    8550 |      -7.22146e+06 |  -844.615 |
| structure_stop                   |    4911 | -506649           |  -103.166 |

### By year

|   year |   count |               sum |     mean |
|-------:|--------:|------------------:|---------:|
|   2020 |    1815 | -651646           | -359.034 |
|   2021 |    2393 | -726657           | -303.659 |
|   2022 |    2155 |      -1.14911e+06 | -533.228 |
|   2023 |    2066 | -634408           | -307.07  |
|   2024 |    1981 | -691246           | -348.938 |
|   2025 |    2494 |      -1.73363e+06 | -695.121 |
|   2026 |     994 | -852228           | -857.373 |