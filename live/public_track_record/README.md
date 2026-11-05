# Public track-record exporters (private)

Sanitized **tear-sheet** JSON for the public GitHub Pages site.

- Growth of $100,000 (additive; **no** size-ups)
- LIVE/SIM vs BACKTEST separated (no blended chart)
- **No** SPY / benchmark overlay
- No instruments, hub paths, or fill tapes in the public repo

| Public name | Private sleeve | Default base size |
|---|---|---|
| FX Momentum | Asia-range London filtered | Live lot-cash (micro fills normalized) |
| FX Intraday Trend | Monday OR ungated demo book | Research / live book as exported |
| Index Momentum | Clean-break pyramid trail | **10× deployment-capped research unit** (entry/add 10 / hard max 30); legacy qty=1 practice fills renormalized to that base |

```bash
export PYTHONPATH="/home/tester/hsm:/home/tester/hsm/potions/v20-python/src"
./scripts/update_public_track_record.sh --email
```

Skill: `.cursor/skills/potions-public-track-record/SKILL.md`
