"""Refresh deterministic hub snapshot / email artifacts after a research job.

Thin wrapper so family drivers can call one function without importing the
full snapshot CLI surface.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional, Sequence

from .hub_snapshot import (
    _email_subject,
    build_snapshot,
    load_prior_snapshot,
    maybe_attach_exit_attribution,
    write_snapshot_artifacts,
)

REPO = Path(__file__).resolve().parents[1]


def refresh_hub_snapshot(
    hub: Path,
    *,
    markets: Optional[Sequence[str]] = None,
    email: bool = False,
) -> Dict[str, Any]:
    hub = Path(hub)
    if not hub.is_absolute():
        hub = REPO / hub
    prior = load_prior_snapshot(hub)
    # Prefer LATEST as prior when it exists (immediately preceding live state)
    latest = hub / "LATEST_SNAPSHOT.json"
    if latest.exists():
        try:
            prior = json.loads(latest.read_text(encoding="utf-8"))
        except Exception:
            pass
    snap = build_snapshot(hub, markets=markets, prior=prior)
    maybe_attach_exit_attribution(hub, snap)
    write_snapshot_artifacts(hub, snap, email=email)
    return snap


def email_subject_for_hub(hub: Path) -> str:
    hub = Path(hub)
    if not hub.is_absolute():
        hub = REPO / hub
    latest = hub / "LATEST_SNAPSHOT.json"
    if latest.exists():
        try:
            return _email_subject(json.loads(latest.read_text(encoding="utf-8")))
        except Exception:
            pass
    return "potions: %s INTERIM SNAPSHOT" % hub.name
