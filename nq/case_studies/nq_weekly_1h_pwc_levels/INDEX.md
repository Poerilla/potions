# NQ Weekly 1h Level Study

**1-hour** NQ candles, **Sunday–Friday** (Saturday omitted; Friday clipped at 16:00 NY).

### Levels (prior completed W-SUN week)
- **PWH / PWL** — previous week high / low
- **PWC / PWO** — previous week close / open
- **PW 50%** — dashed midpoint of prior week range
- **WO** — current week open (green)

### ATR bands (shaded)
Anchor = **current week open (WO)**. ATR = **daily ATR(14)** as of week open (causal: last completed day before the week).
Shaded: WO±1 ATR (darker) and WO±2 ATR (lighter outer), clipped to the week’s price range for readability.

- Week charts: `104` under [`weeks/`](weeks/)
- Month charts: `25` under [`months/`](months/)

Regenerate: `python3 nq/case_studies/build_nq_weekly_1h_level_study.py`