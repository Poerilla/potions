# touch_st_align — structural validity vs entry level

PaperBroker campaigns joined to reconstructed touch→through→ST-flip signals.

## Validity classes (at fill vs structure key)

- **reclaimed** — fill on the program side of the key (long ≥ key / short ≤ key)
- **still_through** — fill still through the broken key (<25 pts)
- **deep_through** — still through and ≥25 pts beyond the key
- **unmatched** — no analytic twin within ~5 minutes

## Coverage

- Campaigns: **1391** · matched: **434** (31.2%)

## By validity

| validity      |   n |              net |   wr_pct |
|:--------------|----:|-----------------:|---------:|
| deep_through  | 222 | -24182.5         |     45   |
| reclaimed     | 147 | -11332.5         |     49   |
| still_through |  65 | 135775           |     56.9 |
| unmatched     | 957 |     -1.34694e+06 |     43.8 |

## Matched only — PnL split

- reclaimed net **$-11332** (n=147)
- still_through net **$135775** (n=65)
- deep_through net **$-24182** (n=222)

### Minutes through before flip (matched)

- reclaimed: median **29** min · p75 **65** · share ≥20m **63.3%**
- still_through: median **47** min · p75 **85** · share ≥20m **95.4%**
- deep_through: median **76** min · p75 **132** · share ≥20m **95.0%**

### If we had skipped still_through + deep_through

- Keep reclaimed only: n=147 net **$-11332** WR 49.0%
- Dropped through entries: n=287 net **$111592**

## Read

Continuation entries that fire while price is still through the structure are structurally faded (buying broken support / selling broken resistance). A 20-minute still-through fade path would harvest that regime instead of waiting for an aligned ST flip into the broken level.

Artifacts: `campaign_validity.csv`, `analytic_signals.csv`.

## Broader day-key coverage (fill vs same-day bull/bear key)

Uses end-of-day structure keys for the entry session (higher coverage than signal twin).

| validity | n | net | wr% |
|---|---:|---:|---:|
| deep_through | 416 | $-670466 | 43.0 |
| reclaimed | 874 | $-581552 | 45.5 |
| still_through | 88 | $19695 | 48.9 |

- Through share: **36.6%** (deep **30.2%**)
- Reclaimed-only net: **$-581552** (n=874)
- Through entries net: **$-650771** (n=504)
