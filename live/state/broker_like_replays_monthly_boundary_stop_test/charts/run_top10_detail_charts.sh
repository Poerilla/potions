#!/usr/bin/env bash
set -euo pipefail

cd /home/tester/hsm

python3 -m potions.live.build_broker_like_replay_detail_charts \
  --replay-root potions/live/state/broker_like_replays_monthly_boundary_stop_test \
  --output-root potions/live/state/broker_like_replays_monthly_boundary_stop_test/charts/detail \
  --exact \
  --slug ym_monthly_orb_restricted_scaleout3_boundary_stop \
  --slug nq_atr_daily_ladder112221_10max \
  --slug mnq_atr_daily_ladder112221_10max \
  --slug nq_atr_daily_3initial_10max \
  --slug mnq_atr_daily_3initial_10max \
  --slug es_atr_weekly_2initial_3add_6max \
  --slug es_monthly_orb_restricted_scaleout3_boundary_stop \
  --slug mym_monthly_orb_restricted_scaleout3_boundary_stop \
  --slug mes_monthly_orb_restricted_scaleout3_boundary_stop \
  --slug nq_atr_weekly_2initial_3add_6max
