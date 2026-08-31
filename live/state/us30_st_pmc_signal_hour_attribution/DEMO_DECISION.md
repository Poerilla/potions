# Demo decision — demo_us30_hourly_st_pmc

```yaml
demo_us30_hourly_st_pmc:
  alpha_status: invalidated
  action_preferred: stop
  action_if_retained:
    purpose: "OANDA lifecycle / broker reconciliation control only"
    quantity: minimum
    risk_budget: zero
    performance_reporting: excluded
    deadline: "fixed — stop alpha reporting immediately; sunsets after 20 further campaigns or 2026-09-30, whichever first"
```

Do **not** continue calling it an alpha demo. Paper/live P&L from this book must not
affect conclusions about the US30 ST+PMC strategy. The old fair-3R N/S 29.39 record
is an audit lesson under invalid left-label timing; revival requires a **new**
causal mechanism (paths A/B/C), not an exit tweak.
