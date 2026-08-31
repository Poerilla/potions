# CHOP20 Dynamic Range — 1m Cross-Market Path Proof

Variant: `touch_broken_boundary_max_age_60`

- Daily CHOP20 range + close breakout = **signal only**
- Entry = daily close (+1 tick adverse) at last RTH 1m
- Stop = touch broken range boundary; targets 0.5R / 1R / 4R
- Max range age = 60 daily bars; **stop-first** same-bar on 1m
- Path-aware pandas replay (not StrategyPlugin yet)

| Market | Trades | Net | MTM DD | N/S | WR | Long | Short |
|---|---:|---:|---:|---:|---:|---:|---:|
| NQ | 69 | $+470087 | $-68679 | 6.84 | 38% | $+421236 | $+48852 |
| MNQ | 31 | $+23106 | $-6886 | 3.36 | 42% | $+16280 | $+6826 |
| YM | 98 | $-6214 | $-118738 | -0.05 | 28% | $+107853 | $-114066 |
| MYM | 48 | $-2981 | $-10604 | -0.28 | 17% | $+5794 | $-8775 |

**Stance:** research — structure portable on best markets; see HA mill / causality

DSR: `TRL-2026-00177`

Hub: `/home/tester/hsm/potions/live/state/chop20_dynamic_range_1m_boundary60_xmarket`
