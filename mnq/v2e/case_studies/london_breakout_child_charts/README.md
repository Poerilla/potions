# London breakout + child limits — chart sample

Visual check for ``../scripts/london_breakout_child.py``: first **5 m close** outside London, then **green** (long) / **red** (short) **child** 5 m bars fully outside the box; **limits at child opens** (live after child close); up to **5** scale-ins; SL/TP per script.

Month-stratified sample: **20** sessions with ≥1 fill.

```bash
cd potions/mnq/v2e/scripts
python3 build_london_breakout_child_charts.py --max-charts 20
```
