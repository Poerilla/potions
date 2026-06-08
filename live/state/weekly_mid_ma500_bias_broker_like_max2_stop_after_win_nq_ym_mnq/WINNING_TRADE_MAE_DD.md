# Winning Trade Adverse Excursion

Broker-like max-2 / stop-after-first-win run. `mae_dd_pts` is the worst open adverse move in points during each winning trade, reconstructed from persisted 15-minute replay bars.

| Market | Winning Trades | Avg DD Pts | Median DD Pts | P90 DD Pts | Max DD Pts | Avg Profit Pts | CSV |
|---|---:|---:|---:|---:|---:|---:|---|
| NQ | 175 | 20.30 | 18.75 | 41.07 | 48.88 | 126.87 | [audits/nq_weekly_mid_ma500_bias/winning_trade_mae_dd_pts.csv](audits/nq_weekly_mid_ma500_bias/winning_trade_mae_dd_pts.csv) |
| YM | 140 | 24.00 | 22.00 | 45.05 | 49.00 | 233.23 | [audits/ym_weekly_mid_ma500_bias/winning_trade_mae_dd_pts.csv](audits/ym_weekly_mid_ma500_bias/winning_trade_mae_dd_pts.csv) |
| MNQ | 69 | 22.12 | 20.25 | 43.90 | 49.50 | 225.15 | [audits/mnq_weekly_mid_ma500_bias/winning_trade_mae_dd_pts.csv](audits/mnq_weekly_mid_ma500_bias/winning_trade_mae_dd_pts.csv) |