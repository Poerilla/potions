# Monday OR sizing sweep — adapted plan

## What we actually have

- **Main:** Mon OR breakout, 3 / drop2@30 / cut1@50, SL=1R TP=2R, HTF both-opposed skip.
- **Sidecar:** **shifted primary** (opposite Mon extreme after flat@50%), **not**
  same-direction re-entry at the symbolic SL.
- **Weekly cap:** max N primary trades/week (baseline N=2). Sidecar does not consume the cap.
- **Sessions:** Tue–Fri full week (no London/NY hour filter yet — Phase 2).

## Dimensions

| Dim | Meaning | Phase 1 | Full |
|---|---|---|---|
| M* | Main entry + (qty@30%, qty@50%) | M1–M3 | M1–M6 |
| S* | Shifted sidecar sizing | S1–S3 | S1–S5 |
| R* | Max primary trades/week | R1=2, R2=3, R3=99 | same |

## Selection

Among cells with Net/|DD| ≥ baseline×0.95 and PF ≥ 1.05, pick highest Net/|DD|,
then highest ≈USD net. Confirm top cells on USDJPY (viability pair).

Baseline tag: **M1_S1_R1** (current research champion structure).
