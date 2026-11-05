#!/usr/bin/env bash
set -euo pipefail
ROOT="/home/tester/hsm/potions"
export PYTHONPATH="/home/tester/hsm:/home/tester/hsm/potions/v20-python/src"
cd "$ROOT"
HUB="live/state/usdjpy_fbo_113_atr80_rsi_with_side_arm_skip_1m_broker"
mkdir -p "$HUB"
nohup python -m live.usdjpy_fbo_113_atr80_rsi55_70_broker \
  --tf 1m \
  --arm-policy skip_candidate \
  --arm-rsi-buckets rsi_with_side \
  --force \
  --email \
  >"$HUB/run.log" 2>&1 &
echo "Started rsi_with_side follow-up pid=$! hub=$HUB"
