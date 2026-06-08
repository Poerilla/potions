# v2d regime — winners vs losers

Charts are built only for sessions where the **adaptive 50/150 routing would trade v2d**
(`Regime=v2d`: prior MNQ daily close had MA50 ≤ MA150).

- **`winners/`** — sampled calendar days with **positive** Σ Net_$ across `Regime=v2d` legs that day.
- **`losers/`** — sampled days with **negative** Σ Net_$.

Leg data come from [`orb_adaptive_50_150_child.py`](../../v2d/orb_adaptive_50_150_child.py) output (includes fade fills + optional children + timestamps). Charts reuse [`../v2b_c/build_case_studies.py`](../v2b_c/build_case_studies.py) rendering (`tier1 fade` labels).

```bash
cd /home/tester/hsm/potions/mnq/case_studies/v2d_regime_case_studies
python3 build_v2d_winners_losers.py --help
python3 build_v2d_winners_losers.py --n-per-bucket 18 --seed 44 --start 2024-01-01
```

See **`INDEX.md`** after a run.
