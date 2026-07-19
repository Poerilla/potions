# EURUSD Intraday MA / SuperTrend Research

Window: **2015-01-01 → 2026-03-31** (America/New_York). Session: London 08:00 → NY 16:00.

Fee $1.50/unit · ~0.5 pip half-spread · completed-bar causal pandas path.

| Strategy | Trades | Net | Closed DD | Net/DD | Win% | PF |
|---|---:|---:|---:|---:|---:|---:|
| st_dca_15m_atr14x3_0p5x5_london_ny | 12505 | $337,165 | $-14,821 | 22.749 | 30.35 | 1.237 |
| st_break_5m_atr14x3_london_ny | 24169 | $60,002 | $-17,538 | 3.421 | 26.06 | 1.064 |
| st_break_3m_atr14x3_london_ny | 38655 | $-17,814 | $-53,849 | -0.331 | 25.84 | 0.986 |
| ma3_ema9_21_50_15m_follow_pmc | 4688 | $-41,205 | $-52,745 | -0.781 | 30.87 | 0.905 |
| ma3_ema9_21_50_15m_opposing_pmc | 3541 | $-57,018 | $-62,016 | -0.919 | 28.38 | 0.824 |
| ma3_ema9_21_50_5m_follow_pmc | 10099 | $-109,950 | $-117,301 | -0.937 | 28.36 | 0.818 |
| ma3_ema9_21_50_5m_opposing_pmc | 8615 | $-118,106 | $-119,544 | -0.988 | 25.97 | 0.76 |

## Rules

- **3-MA:** EMA 9/21/50 stack; long on bull stack, short on bear; `follow` = side with PMC, `opposing` = fade PMC.
- **ST break 3m/5m:** long when prior bearish trail taken; short when prior bullish trail taken; SL trails at current SuperTrend; flatten at NY close.
- **15m ST DCA:** 0.5 lot adds while ST side holds, max 5; exit on trail hit.

Baseline FX sleeve (promoted): Hourly ST+PMC 25/75 MA bull ~$23.5k / 1.49 Net/Stress (full sample 2003–2026).

## Read

- **3-MA + PMC (follow and opposing):** both lose. Stack-follow with PMC is not an edge here.
- **3m ST break:** slight loss; too noisy.
- **5m ST break:** positive (~$60k / ~3.4 Net/closed-DD) but year path is lumpy (strong 2015/2022, several red years).
- **15m ST DCA 0.5×5:** strongest on this pass (~$337k). Mean size ~1.9 lots (often hits 2.5). **DD is closed-equity only** (not open multi-unit intrabar stress), so Net/DD is optimistic vs broker-like stress. Needs Engine + PaperBroker confirmation before any promotion.

Driver: `live/eurusd_intraday_ma_st_research.py`
