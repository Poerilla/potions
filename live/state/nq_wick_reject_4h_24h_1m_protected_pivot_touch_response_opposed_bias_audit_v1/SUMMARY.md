NQ 4H WICK-REJECT -> 24H 1M PROTECTED-AREA
OPPOSED-BIAS MIRROR AUDIT V1

STATUS:
DESCRIPTIVE ONLY / MATHEMATICAL MIRROR AUDIT

PARENT:
nq_wick_reject_4h_24h_1m_protected_pivot_touch_response_v1

PARENT CONFIG HASH:
402795e0a05e2fbc

RECONCILIATION:
PASS

Population matching
- Parent eligible seeds / audit eligible seeds: 91 / 91
- Parent candidates / audit candidates: 90 / 90
- Parent bear / audit bear: 52 / 52
- Parent bull / audit bull: 38 / 38
- Parent structure evaluable / audit structure evaluable:
  bear 39 / 39
  bull 32 / 32
- Parent contact evaluable / audit contact evaluable:
  bear 34 / 34
  bull 29 / 29

Structure completion, unchanged 180-minute windows
- Bear original RR / opposed RR: 0.338 / 2.957
- Bear reciprocal identity: PASS
- Bull original RR / opposed RR: 0.671 / 1.490
- Bull reciprocal identity: PASS

Contact reaction, unchanged 60-minute windows
- Bear original MFE / MAE: 144.35 / 137.03 ticks
- Bear opposed MFE / MAE: 137.03 / 144.35 ticks
- Bear original RR / opposed RR: 1.053 / 0.949
- Bear median original RR / opposed RR: 0.826 / 1.181
- Bear concentration: top-1 31.7%, top-3 44.6%

- Bull original MFE / MAE: 104.14 / 106.14 ticks
- Bull opposed MFE / MAE: 106.14 / 104.14 ticks
- Bull original RR / opposed RR: 0.981 / 1.019
- Bull median original RR / opposed RR: 1.268 / 0.788
- Bull concentration: top-1 15.0%, top-3 38.1%

Interpretation
- Opposed-bias values are an inverse labeling of the same parent price paths.
- They do not validate reverse trading.
- They do not authorize a bias selector, entry study, P&L study, or plugin.

Disposition
- Preserve parent study unchanged.
- Preserve this audit unchanged.
- No further reverse-bias variant work on this same sample.

Final language

"This opposed-bias audit uses the exact same candidates, protected areas,
reference prices, first contacts, price windows, and data as the parent
study. It reverses only the label for favorable and adverse movement. The
resulting MFE/MAE and R-to-R values are therefore a mathematical mirror of
the parent measurements, not independent evidence for a reverse trade or
strategy."
