# Dedicated OANDA practice accounts

Primary `101-002-39860312-001` stays **dormant** (no daemons).
Yearly ORB book uses `-002`. Monthly FBO uses `-006`.

| Strategy | Demo dir | Account | Config |
|---|---|---|---|
| NAS100 clean-break trail06_m4_e2_out_be | `nas100_v2b_clean_break_trail06_m4_e2_out_be_oanda` | `101-002-39860312-003` | `nas100_clean_break_trail_003.json` |
| USDJPY Asia Range `S_3_1_3` | `usdjpy_asia_range_london_oanda` | `101-002-39860312-004` | `usdjpy_asia_range_004.json` |
| USDJPY Monday OR M2_S3_R1 | `usdjpy_monday_or_ungated_oanda` | `101-002-39860312-005` | `usdjpy_monday_or_005.json` |
| USDJPY Monthly FBO 1/1/3 atr80 | `usdjpy_monthly_orb_fbo_oanda` | `101-002-39860312-006` | `usdjpy_monthly_fbo_006.json` |

Start (after token can access accounts):

```bash
set -a && source live/demo/.env && set +a
export PYTHONPATH="/home/tester/hsm:/home/tester/hsm/potions/v20-python/src"
CFG=/home/tester/hsm/potions/live/demo/oanda_account_configs
# Prefer absolute --oanda-config paths (Monday OR spawn cwd is hsm/, not potions/).
python3 -m potions.live.cli demo-nas100-clean-break-trail-oanda --daemon \
  --oanda-config "$CFG/nas100_clean_break_trail_003.json"
python3 -m potions.live.cli demo-usdjpy-asia-range-oanda --daemon \
  --oanda-config "$CFG/usdjpy_asia_range_004.json"
python3 -m potions.live.cli demo-usdjpy-monday-or-oanda --daemon \
  --oanda-config "$CFG/usdjpy_monday_or_005.json"
python3 -m potions.live.cli demo-usdjpy-monthly-fbo-oanda --daemon \
  --oanda-config "$CFG/usdjpy_monthly_fbo_006.json"
```

**2026-08-20 15:22Z:** token OK; original three UP on dedicated accounts (streams 200).

**2026-08-24 rotation:** account `-004` replaced NAS100 ST+PMC 2R->10R with
USDJPY Asia Range `S_3_1_3` after the USDJPY StrategyPlugin causality review
passed at 1m bar resolution. See `usdjpy_asia_range_004_META.json`.

**2026-08-26:** account `-006` reserved for USDJPY Monthly ORB FBO 1/1/3 atr80
(best monthly FX/metal/CFD broker book, N/S 4.25). Wire-up ready; token listed
the account but `/v3/accounts/…-006` returned **403 Forbidden** until practice
API access is granted for the new sub-account. See `usdjpy_monthly_fbo_006_META.json`.

**2026-08-31 rotation:** account `-003` replaced Fair US30 ST+PMC 3R with
NAS100 clean-break `trail06_m4_e2_out_be` (best NAS100 N/S in CFD top-3;
1m-fill validation `brl_21741b260a28`). See `nas100_clean_break_trail_003_META.json`.
OANDA alias updated the same day: `Fair US30` → `NAS100 Clean Break Trail06`.
