"""Attribute practice-account balance / realized PL from OANDA transactions.

Practice only. Read-only (no place/cancel). Writes under
``live/demo/oanda_practice_snapshot/``:

- ``transactions_all.json``
- ``PL_ATTRIBUTION.json``
- ``PL_ATTRIBUTION.md``
- ``EMAIL_PL_ATTRIBUTION.txt``

Usage::

    export PYTHONPATH="/home/tester/hsm:/home/tester/hsm/potions/v20-python/src"
    set -a && source live/demo/.env && set +a
    python3 -m potions.live.demo.oanda_pl_attribution --email
    # or: python3 -m potions.live.cli oanda-pl-attribution --email
"""

from __future__ import annotations

import argparse
import json
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from ..notify_email import send_email
from ..oanda import OandaApiClient, OandaConfig
from ..store import FlatFileStore
from . import DEMO_ROOT

SNAP_ROOT = DEMO_ROOT / "oanda_practice_snapshot"
INSTRUMENT_ROLE = {
    "NAS100_USD": "v2b ungated NAS100 (shared account; ST+PMC may share tape)",
    "US30_USD": "v2b ungated US30 (shared account; ST+PMC / london may share)",
    "SPX500_USD": "v2b ungated SPX500",
    "EUR_USD": "v2b / ST+PMC EURUSD",
    "USD_JPY": "Monday OR / Asia-range USDJPY",
    "AUD_JPY": "yearly ORB AUDJPY",
    "XAU_USD": "yearly ORB XAUUSD",
    "XAG_USD": "yearly ORB XAGUSD",
}


def _as_dict(obj: Any) -> Dict[str, Any]:
    if obj is None:
        return {}
    if isinstance(obj, dict):
        return obj
    if hasattr(obj, "dict") and callable(obj.dict):
        try:
            return obj.dict()
        except Exception:
            pass
    out: Dict[str, Any] = {}
    for key in dir(obj):
        if key.startswith("_"):
            continue
        try:
            value = getattr(obj, key)
        except Exception:
            continue
        if callable(value):
            continue
        out[key] = value
    return out


def _f(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _account_fields(client: OandaApiClient) -> Dict[str, Any]:
    raw = client.ctx.account.get(client.config.account_id).body
    account = getattr(raw, "account", None)
    if account is None and isinstance(raw, dict):
        account = raw.get("account") or raw
    acc = _as_dict(account)
    return {
        "fetched_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "env": client.config.env,
        "account_id": client.config.account_id,
        "NAV": _f(getattr(account, "NAV", None) if account is not None else acc.get("NAV")),
        "balance": _f(getattr(account, "balance", None) if account is not None else acc.get("balance")),
        "unrealizedPL": _f(
            getattr(account, "unrealizedPL", None) if account is not None else acc.get("unrealizedPL")
        ),
        "resettablePL": _f(
            getattr(account, "resettablePL", None) if account is not None else acc.get("resettablePL")
        ),
        "financing": _f(
            getattr(account, "financing", None) if account is not None else acc.get("financing")
        ),
        "pl": _f(getattr(account, "pl", None) if account is not None else acc.get("pl")),
        "lastTransactionID": str(
            getattr(account, "lastTransactionID", None)
            if account is not None
            else acc.get("lastTransactionID")
            or ""
        ),
        "openTradeCount": int(
            getattr(account, "openTradeCount", None)
            if account is not None
            else acc.get("openTradeCount")
            or 0
        ),
    }


def _open_trades(client: OandaApiClient) -> List[Dict[str, Any]]:
    body = client.ctx.trade.list_open(client.config.account_id).body
    raw = body.get("trades") if isinstance(body, dict) else getattr(body, "trades", None)
    out: List[Dict[str, Any]] = []
    for trade in raw or []:
        t = _as_dict(trade)
        ext = _as_dict(t.get("clientExtensions") or {})
        out.append(
            {
                "instrument": t.get("instrument"),
                "units": t.get("currentUnits") or t.get("initialUnits"),
                "price": t.get("price"),
                "unrealizedPL": _f(t.get("unrealizedPL")),
                "tag": ext.get("tag") or "",
            }
        )
    return out


def fetch_transactions(client: OandaApiClient, *, last_id: int, chunk: int = 200) -> List[Dict[str, Any]]:
    """Pull idrange history in chunks. OANDA IDs may have gaps; missing IDs are skipped."""

    all_tx: List[Dict[str, Any]] = []
    start = 1
    while start <= last_id:
        end = min(start + max(1, chunk) - 1, last_id)
        resp = client.ctx.transaction.range(
            client.config.account_id,
            fromID=str(start),
            toID=str(end),
        )
        body = resp.body if isinstance(resp.body, dict) else _as_dict(resp.body)
        if body.get("errorMessage"):
            # Fall back to since-page near the end if range fails mid-history.
            print("range error %s-%s: %s" % (start, end, body.get("errorMessage")), flush=True)
            start = end + 1
            time.sleep(0.2)
            continue
        txs = body.get("transactions") or []
        for tx in txs:
            all_tx.append(_as_dict(tx))
        print("transactions %s-%s: +%d (total %d)" % (start, end, len(txs), len(all_tx)), flush=True)
        start = end + 1
        time.sleep(0.05)

    # Catch recent txs that range chunks may have sparse-skipped near the tip.
    since_id = max(1, last_id - 500)
    resp = client.ctx.transaction.since(client.config.account_id, id=str(since_id))
    body = resp.body if isinstance(resp.body, dict) else _as_dict(resp.body)
    by_id = {str(t.get("id")): t for t in all_tx if t.get("id") is not None}
    for tx in body.get("transactions") or []:
        t = _as_dict(tx)
        tid = str(t.get("id") or "")
        if tid and tid not in by_id:
            all_tx.append(t)
            by_id[tid] = t
    all_tx.sort(key=lambda t: int(t.get("id") or 0))
    return all_tx


def _extract_tag(tx: Dict[str, Any]) -> str:
    blobs: List[Any] = []
    for key in ("tradeOpened", "tradeReduced"):
        if tx.get(key):
            blobs.append(tx.get(key))
    closed = tx.get("tradesClosed")
    if isinstance(closed, list):
        blobs.extend(closed)
    elif closed:
        blobs.append(closed)
    for blob in blobs:
        ext = _as_dict(_as_dict(blob).get("clientExtensions") or {})
        tag = str(ext.get("tag") or ext.get("id") or "").strip()
        if tag:
            return tag
    ext = _as_dict(tx.get("clientExtensions") or {})
    return str(ext.get("tag") or "").strip()


def attribute_fills(
    transactions: Sequence[Dict[str, Any]],
) -> Dict[str, Any]:
    by_inst: Dict[str, float] = defaultdict(float)
    by_tag: Dict[str, float] = defaultdict(float)
    by_reason: Dict[str, float] = defaultdict(float)
    wins: List[Dict[str, Any]] = []
    losses: List[Dict[str, Any]] = []
    financing_tx = 0.0
    transfers = 0.0
    start_balance = None

    for tx in transactions:
        typ = str(tx.get("type") or "")
        if typ == "TRANSFER_FUNDS":
            transfers += _f(tx.get("amount"))
            if start_balance is None:
                start_balance = _f(tx.get("accountBalance"), transfers)
        elif typ == "DAILY_FINANCING":
            financing_tx += _f(tx.get("financing"))
        elif typ == "ORDER_FILL":
            pl = _f(tx.get("pl"))
            inst = str(tx.get("instrument") or "")
            tag = _extract_tag(tx) or "(no tag)"
            reason = str(tx.get("reason") or "")
            by_inst[inst] += pl
            by_tag[tag] += pl
            by_reason[reason] += pl
            if abs(pl) > 1e-12:
                row = {
                    "id": tx.get("id"),
                    "time": str(tx.get("time") or ""),
                    "instrument": inst,
                    "pl": pl,
                    "units": tx.get("units"),
                    "price": tx.get("price"),
                    "reason": reason,
                    "tag": tag,
                }
                (wins if pl > 0 else losses).append(row)

    ids = sorted(int(t["id"]) for t in transactions if str(t.get("id") or "").isdigit())
    missing: List[int] = []
    if ids:
        have = set(ids)
        missing = [i for i in range(ids[0], ids[-1] + 1) if i not in have]

    return {
        "by_instrument": dict(sorted(by_inst.items(), key=lambda kv: -kv[1])),
        "by_tag": dict(sorted(by_tag.items(), key=lambda kv: -abs(kv[1]))),
        "by_reason": dict(sorted(by_reason.items(), key=lambda kv: -abs(kv[1]))),
        "wins": sorted(wins, key=lambda r: -r["pl"]),
        "losses": sorted(losses, key=lambda r: r["pl"]),
        "fill_pl_total": float(sum(by_inst.values())),
        "financing_tx_sum": financing_tx,
        "transfers_sum": transfers,
        "start_balance_hint": start_balance,
        "n_transactions": len(transactions),
        "tx_type_counts": dict(Counter(str(t.get("type")) for t in transactions)),
        "missing_tx_ids_count": len(missing),
        "missing_tx_ids_sample": missing[:20],
    }


def render_markdown(
    account: Dict[str, Any],
    attr: Dict[str, Any],
    open_trades: Sequence[Dict[str, Any]],
) -> str:
    bal = _f(account.get("balance"))
    nav = _f(account.get("NAV"))
    upl = _f(account.get("unrealizedPL"))
    reset = _f(account.get("resettablePL"))
    fin = _f(account.get("financing"))
    start = _f(attr.get("start_balance_hint"), 100000.0)
    lines = [
        "# OANDA practice PL attribution",
        "",
        "Fetched: `%s`  Account: `%s` (%s)"
        % (account.get("fetched_at"), account.get("account_id"), account.get("env")),
        "",
        "## Balance vs trading PnL",
        "",
        "- **Balance** (what the UI often shows as a big number): **$%.2f**" % bal,
        "- NAV: **$%.2f** (balance + unrealized **$%.2f**)" % (nav, upl),
        "- Broker `resettablePL` (realized): **$%.2f**" % reset,
        "- Broker financing field: **$%.2f**" % fin,
        "- Starting deposit hint: **$%.2f**" % start,
        "- Bridge check: `start + resettablePL + financing ≈ $%.2f`" % (start + reset + fin),
        "",
        "If the user quotes ~balance (e.g. 100895), say clearly: that is **account balance**, not trading PnL.",
        "",
        "## Realized ORDER_FILL PL by instrument",
        "",
        "| Instrument | Fill PL | Role |",
        "|---|---:|---|",
    ]
    for inst, pl in (attr.get("by_instrument") or {}).items():
        if not inst and abs(_f(pl)) < 1e-9:
            continue
        lines.append(
            "| `%s` | $%.2f | %s |"
            % (inst or "(none)", _f(pl), INSTRUMENT_ROLE.get(str(inst), ""))
        )
    lines.append("| **Sum of fill PL** | **$%.2f** | |" % _f(attr.get("fill_pl_total")))
    wins = attr.get("wins") or []
    losses = attr.get("losses") or []
    lines.extend(
        [
            "",
            "Closing fills with PL: **%d wins / $%.2f** vs **%d losses / $%.2f**."
            % (
                len(wins),
                sum(_f(r["pl"]) for r in wins),
                len(losses),
                sum(_f(r["pl"]) for r in losses),
            ),
            "",
            "### By exit / fill reason",
            "",
        ]
    )
    for reason, pl in (attr.get("by_reason") or {}).items():
        if abs(_f(pl)) < 1e-6:
            continue
        lines.append("- `%s`: $%.2f" % (reason, _f(pl)))
    if attr.get("by_tag"):
        lines.extend(["", "### By clientExtensions.tag", ""])
        for tag, pl in (attr.get("by_tag") or {}).items():
            if abs(_f(pl)) < 1e-6:
                continue
            lines.append("- `%s`: $%.2f" % (tag, _f(pl)))
    lines.extend(["", "### Largest losses", ""])
    for row in losses[:10]:
        lines.append(
            "- %s `%s` **$%.2f** units=%s `%s`"
            % (
                str(row.get("time") or "")[:19],
                row.get("instrument"),
                _f(row.get("pl")),
                row.get("units"),
                row.get("reason"),
            )
        )
    lines.extend(["", "### Largest wins", ""])
    for row in wins[:10]:
        lines.append(
            "- %s `%s` **$%.2f** units=%s `%s`"
            % (
                str(row.get("time") or "")[:19],
                row.get("instrument"),
                _f(row.get("pl")),
                row.get("units"),
                row.get("reason"),
            )
        )
    lines.extend(["", "## Open trades", ""])
    if not open_trades:
        lines.append("(flat)")
    else:
        for tr in open_trades:
            lines.append(
                "- `%s` units=%s unrealized **$%.2f** avg=%s tag=%s"
                % (
                    tr.get("instrument"),
                    tr.get("units"),
                    _f(tr.get("unrealizedPL")),
                    tr.get("price"),
                    tr.get("tag") or "(none)",
                )
            )
    lines.extend(
        [
            "",
            "## Caveats",
            "",
            "- Prefer broker `resettablePL` + financing for the **balance bridge**.",
            "- Prefer ORDER_FILL `pl` totals for **which instruments / exit types** made or lost money.",
            "- Sum(fill PL) may disagree with `resettablePL` when OANDA transaction IDs have gaps "
            "(`missing_tx_ids_count=%s`)."
            % attr.get("missing_tx_ids_count"),
            "- Strategy tags are often empty on fills; instrument is the practical attribution key.",
            "",
            "Artifacts: `transactions_all.json`, `PL_ATTRIBUTION.json`, this file.",
            "",
        ]
    )
    return "\n".join(lines)


def run(*, email: bool = False) -> Path:
    config = OandaConfig.from_env()
    config.validate_for_network()
    if str(config.env).lower() != "practice":
        raise RuntimeError("oanda_pl_attribution is practice-only; got env=%r" % config.env)
    SNAP_ROOT.mkdir(parents=True, exist_ok=True)
    store = FlatFileStore(SNAP_ROOT / "_broker_scratch")
    store.ensure()
    client = OandaApiClient(config=config, store=store)
    account = _account_fields(client)
    last_id = int(account.get("lastTransactionID") or 0)
    if last_id <= 0:
        raise RuntimeError("account lastTransactionID missing")
    transactions = fetch_transactions(client, last_id=last_id)
    (SNAP_ROOT / "transactions_all.json").write_text(json.dumps(transactions, default=str))
    attr = attribute_fills(transactions)
    open_trades = _open_trades(client)
    summary = {
        "account": account,
        "attribution": {
            "by_instrument": attr["by_instrument"],
            "by_tag": attr["by_tag"],
            "by_reason": attr["by_reason"],
            "fill_pl_total": attr["fill_pl_total"],
            "wins_usd": sum(_f(r["pl"]) for r in attr["wins"]),
            "losses_usd": sum(_f(r["pl"]) for r in attr["losses"]),
            "n_wins": len(attr["wins"]),
            "n_losses": len(attr["losses"]),
            "financing_tx_sum": attr["financing_tx_sum"],
            "transfers_sum": attr["transfers_sum"],
            "missing_tx_ids_count": attr["missing_tx_ids_count"],
            "n_transactions": attr["n_transactions"],
        },
        "open_trades": open_trades,
        "top_wins": attr["wins"][:15],
        "top_losses": attr["losses"][:15],
    }
    (SNAP_ROOT / "PL_ATTRIBUTION.json").write_text(json.dumps(summary, indent=2, default=str) + "\n")
    md = render_markdown(account, attr, open_trades)
    md_path = SNAP_ROOT / "PL_ATTRIBUTION.md"
    md_path.write_text(md)
    email_path = SNAP_ROOT / "EMAIL_PL_ATTRIBUTION.txt"
    email_path.write_text(md)
    if email:
        send_email(
            subject="potions: OANDA practice PL attribution (balance $%.2f)"
            % _f(account.get("balance")),
            body=md,
        )
    print("Wrote %s" % md_path, flush=True)
    return md_path


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Attribute OANDA practice account PL from transactions.")
    p.add_argument("--email", action="store_true", help="Email PL_ATTRIBUTION.md via Resend.")
    return p


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    run(email=bool(args.email))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
