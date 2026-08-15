# OR Profile Engine — pooled master (2026H2fx)

Per-market tables live in `<market>/2026H2fx/`. Headline P(hit 1R | first break) and P(hit 2R | hit 1R) across markets:

| Market | Trigger | N breaks | P(1R\|break) | P(2R\|1R) | P(reentry\|break) | P(opp 1R\|fakeout opp break) |
|---|---|---:|---:|---:|---:|---:|
| EURUSD_LONDON | touch | 5959 | 0.867 | 0.839 | 0.974 | 0.195 |
| EURUSD_LONDON | close5 | 5957 | 0.890 | 0.847 | 0.945 | 0.439 |
| EURUSD_NY | touch | 5952 | 0.769 | 0.747 | 0.948 | 0.253 |
| EURUSD_NY | close5 | 5948 | 0.817 | 0.746 | 0.893 | 0.409 |
| USDJPY_NY | touch | 5939 | 0.777 | 0.757 | 0.950 | 0.221 |
| USDJPY_NY | close5 | 5938 | 0.815 | 0.763 | 0.897 | 0.433 |
| XAUUSD_NY | touch | 5643 | 0.801 | 0.785 | 0.964 | 0.211 |
| XAUUSD_NY | close5 | 5643 | 0.836 | 0.788 | 0.922 | 0.388 |
