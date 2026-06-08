from __future__ import annotations

from dataclasses import replace
from typing import Optional

from .models import OrderIntent, VerificationRequest, as_row, new_id, utc_now_iso
from .store import FlatFileStore


class VerificationProvider:
    def request_verification(self, intent: OrderIntent) -> VerificationRequest:
        raise NotImplementedError

    def is_approved(self, verification_id: str) -> bool:
        raise NotImplementedError


class SpoofVerificationProvider(VerificationProvider):
    """Spoofed 2FA.

    Paper mode auto-approves. Live mode creates a pending verification unless
    auto_approve_live is explicitly enabled for rehearsal.
    """

    def __init__(self, store: FlatFileStore, auto_approve_live: bool = False):
        self.store = store
        self.auto_approve_live = auto_approve_live
        self.store.ensure()

    def request_verification(self, intent: OrderIntent) -> VerificationRequest:
        approved = intent.account_mode == "paper" or self.auto_approve_live
        now = utc_now_iso()
        req = VerificationRequest(
            verification_id=new_id("verify"),
            intent_id=intent.intent_id,
            strategy_id=intent.strategy_id,
            account_mode=intent.account_mode,
            status="approved" if approved else "pending",
            challenge="SPOOF-%s" % intent.intent_id[-6:],
            created_at=now,
            approved_at=now if approved else "",
        )
        self.store.upsert_row("pending_verifications", "verification_id", as_row(req))
        self.store.append_event("verifications", as_row(req))
        return req

    def is_approved(self, verification_id: str) -> bool:
        for row in self.store.read_table("pending_verifications"):
            if row.get("verification_id") == verification_id:
                return row.get("status") == "approved"
        return False

    def approve(self, verification_id: str) -> None:
        for row in self.store.read_table("pending_verifications"):
            if row.get("verification_id") == verification_id:
                row["status"] = "approved"
                row["approved_at"] = utc_now_iso()
                self.store.upsert_row("pending_verifications", "verification_id", row)
                self.store.append_event("verifications", dict(row, event="manual_approve"))
                return
        raise KeyError("Verification not found: %s" % verification_id)


class QuietPaperVerificationProvider(VerificationProvider):
    """Replay-only paper verifier that avoids writing 2FA event spam."""

    def request_verification(self, intent: OrderIntent) -> VerificationRequest:
        now = utc_now_iso()
        return VerificationRequest(
            verification_id="quiet_%s" % intent.intent_id,
            intent_id=intent.intent_id,
            strategy_id=intent.strategy_id,
            account_mode=intent.account_mode,
            status="approved" if intent.account_mode == "paper" else "pending",
            challenge="QUIET",
            created_at=now,
            approved_at=now if intent.account_mode == "paper" else "",
        )

    def is_approved(self, verification_id: str) -> bool:
        return str(verification_id).startswith("quiet_")
