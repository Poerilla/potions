# OR Profile Engine — pooled master (2026H2)

Per-market tables live in `<market>/2026H2/`. Headline P(hit 1R | first break) and P(hit 2R | hit 1R) across markets:

| Market | Trigger | N breaks | P(1R\|break) | P(2R\|1R) | P(reentry\|break) | P(opp 1R\|fakeout opp break) |
|---|---|---:|---:|---:|---:|---:|
| MNQ | touch | 1245 | 0.563 | 0.486 | 0.877 | 0.168 |
| MNQ | close5 | 1244 | 0.624 | 0.488 | 0.797 | 0.265 |
| MYM | touch | 1696 | 0.543 | 0.489 | 0.904 | 0.136 |
| MYM | close5 | 1687 | 0.596 | 0.497 | 0.832 | 0.246 |
| NQ | touch | 3984 | 0.542 | 0.497 | 0.893 | 0.165 |
| NQ | close5 | 3976 | 0.590 | 0.498 | 0.810 | 0.276 |
| YM | touch | 3955 | 0.560 | 0.482 | 0.910 | 0.160 |
| YM | close5 | 3939 | 0.609 | 0.492 | 0.839 | 0.291 |
