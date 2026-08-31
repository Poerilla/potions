# Causality audit — NQ structure-change atlas

- Engine: frozen `StructureProgramEngine` (left/right=2).
- Feature known at structure-bar close; `order_active_ts = feature_available_at + 1m`.
- Forward path uses 1m RTH opens at/after `order_active_ts`.
- Violations `feature_available_at < order_active_ts`: **0 / 3353**.
- Phase 5 strategy claims still require path-aware fills + this audit PASS.

Status: **PASS**
