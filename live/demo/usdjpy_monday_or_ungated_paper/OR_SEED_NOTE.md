NOTE OR_SEED 2026-07-27T09:15:58-04:00
when: 2026-07-27T09:15:58-04:00
why: Paper twin silently dropped all OANDA stream ticks (filtered msg_type=='PRICE' but v20 yields 'pricing.ClientPrice'), so it never built Monday OR (0 ticks / empty bars / health=init). Also appeared 'hung' after 2026-07-27T02:49 stream reconnect because progress heartbeats only fire on processed ticks.
solution: (1) Fixed paper stream loop to match OANDA twin — accept pricing.ClientPrice, skip PricingHeartbeat, parse bids/asks via shared helpers. (2) Copied OANDA USDJPY_1m.csv + USDJPY_15m.csv into paper state/bars. (3) Seeded paper strategy_state with OANDA mon_high=163.7065 mon_low=163.3305 R=0.3760000000000048 week_monday=2026-07-27 so Tue–Fri breakouts have a real Monday OR to execute on. Paper will only expand (not shrink) these extremes on later Monday bars.

