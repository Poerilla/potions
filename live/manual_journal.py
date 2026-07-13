from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence

MANUAL_JOURNAL_FILL_COLUMNS: Sequence[str] = (
    "fill_id",
    "broker_order_id",
    "intent_id",
    "strategy_id",
    "trade_id",
    "instrument",
    "account_mode",
    "side",
    "quantity",
    "price",
    "ts",
    "reason",
    "session_date",
    "order_type",
    "source",
    "notes",
)

REQUIRED_MANUAL_FIELDS = {
    "strategy_id",
    "trade_id",
    "instrument",
    "side",
    "quantity",
    "price",
    "ts",
    "reason",
}

VALID_REASONS = {
    "entry",
    "runner_entry",
    "stop",
    "wide_stop",
    "runner_stop",
    "tp1",
    "tp2",
    "target",
    "eod_close",
    "market_close",
    "manual_exit",
}


@dataclass(frozen=True)
class ManualJournalValidation:
    ok: bool
    errors: List[str]
    row_count: int


def validate_manual_journal_row(row: Dict[str, str], *, row_num: int) -> List[str]:
    errors: List[str] = []
    for field in REQUIRED_MANUAL_FIELDS:
        if not str(row.get(field, "")).strip():
            errors.append("row %d missing required field %s" % (row_num, field))
    reason = str(row.get("reason", "")).strip().lower()
    if reason and reason not in VALID_REASONS:
        errors.append("row %d unknown reason %r (expected one of %s)" % (row_num, reason, sorted(VALID_REASONS)))
    side = str(row.get("side", "")).strip().lower()
    if side and side not in {"buy", "sell"}:
        errors.append("row %d invalid side %r" % (row_num, side))
    qty = str(row.get("quantity", "")).strip()
    if qty:
        try:
            if int(float(qty)) <= 0:
                errors.append("row %d quantity must be positive" % row_num)
        except ValueError:
            errors.append("row %d quantity is not numeric" % row_num)
    price = str(row.get("price", "")).strip()
    if price:
        try:
            float(price)
        except ValueError:
            errors.append("row %d price is not numeric" % row_num)
    return errors


def validate_manual_journal(path: Path) -> ManualJournalValidation:
    errors: List[str] = []
    row_count = 0
    if not path.exists():
        return ManualJournalValidation(False, ["file not found: %s" % path], 0)
    with path.open("r", newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames is None:
            return ManualJournalValidation(False, ["empty CSV"], 0)
        missing_cols = set(MANUAL_JOURNAL_FILL_COLUMNS) - set(reader.fieldnames)
        optional_only = {c for c in missing_cols if c not in REQUIRED_MANUAL_FIELDS}
        if missing_cols - optional_only:
            errors.append("missing columns: %s" % sorted(missing_cols - optional_only))
        for idx, row in enumerate(reader, start=2):
            row_count += 1
            errors.extend(validate_manual_journal_row(row, row_num=idx))
    return ManualJournalValidation(len(errors) == 0, errors, row_count)


def write_manual_journal_template(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(MANUAL_JOURNAL_FILL_COLUMNS))
        writer.writeheader()
        writer.writerow(
            {
                "fill_id": "fill_demo_001",
                "broker_order_id": "ord_demo_001",
                "intent_id": "intent_demo_001",
                "strategy_id": "manual_v2b_session",
                "trade_id": "20260304_01",
                "instrument": "MNQ",
                "account_mode": "paper",
                "side": "buy",
                "quantity": "1",
                "price": "20125.50",
                "ts": "2026-03-04T10:15:00-05:00",
                "reason": "entry",
                "session_date": "2026-03-04",
                "order_type": "market",
                "source": "tradovate_demo",
                "notes": "Replace with exported Tradovate fill",
            }
        )


def normalize_manual_journal_rows(path: Path) -> List[Dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def tradovate_fill_to_journal_row(
    *,
    fill_id: str,
    order_id: str,
    strategy_id: str,
    trade_id: str,
    instrument: str,
    side: str,
    quantity: int,
    price: float,
    ts: str,
    reason: str,
    session_date: str = "",
    order_type: str = "",
    source: str = "tradovate_demo",
    notes: str = "",
) -> Dict[str, str]:
    return {
        "fill_id": fill_id,
        "broker_order_id": order_id,
        "intent_id": "",
        "strategy_id": strategy_id,
        "trade_id": trade_id,
        "instrument": instrument.upper(),
        "account_mode": "paper",
        "side": side.lower(),
        "quantity": str(int(quantity)),
        "price": "%.2f" % float(price),
        "ts": ts,
        "reason": reason.lower(),
        "session_date": session_date or ts[:10],
        "order_type": order_type,
        "source": source,
        "notes": notes,
    }


def export_tradovate_fills(rows: Iterable[Dict[str, str]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(MANUAL_JOURNAL_FILL_COLUMNS))
        writer.writeheader()
        for row in rows:
            writer.writerow({col: str(row.get(col, "")) for col in MANUAL_JOURNAL_FILL_COLUMNS})


def main(argv: Optional[Sequence[str]] = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Validate or scaffold live manual trading journal CSV")
    parser.add_argument("--validate", metavar="PATH", help="Validate fills.csv schema and rows")
    parser.add_argument("--write-template", metavar="PATH", help="Write sample journal template")
    args = parser.parse_args(argv)
    if args.write_template:
        write_manual_journal_template(Path(args.write_template))
        print("Wrote template %s" % args.write_template)
        return 0
    if args.validate:
        result = validate_manual_journal(Path(args.validate))
        print("rows=%d ok=%s" % (result.row_count, result.ok))
        for err in result.errors:
            print(err)
        return 0 if result.ok else 1
    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
