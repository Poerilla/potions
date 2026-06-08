from __future__ import annotations

import argparse
import json
from pathlib import Path

from .engine import Engine, bars_from_csv
from .health import HealthServer
from .models import StrategyInstance, as_row
from .reporting import generate_market_close_report
from .store import FlatFileStore, default_state_root


def _store(args) -> FlatFileStore:
    return FlatFileStore(Path(args.state_root))


def cmd_init(args) -> int:
    store = _store(args)
    store.ensure()
    if args.with_yearly_orb:
        instance = StrategyInstance(
            strategy_id=args.strategy_id,
            strategy_type="yearly_orb_scaleout3",
            version="v1",
            instrument=args.instrument,
            broker_instrument=args.broker_instrument or args.instrument,
            account_mode=args.account_mode,
            enabled=True,
            timeframes="D",
            max_contracts=args.max_contracts,
            max_open_orders=24,
            config_json=json.dumps(
                {
                    "or_start_month": 1,
                    "or_end_month": 3,
                    "trade_start_month": 4,
                    "trade_end_month": 12,
                    "batch_qty": args.batch_qty,
                    "tp25_frac": 0.25,
                    "tp_full_mult": 1.0,
                    "require_fresh_break": True,
                },
                sort_keys=True,
            ),
        )
        store.upsert_row("strategy_instances", "strategy_id", as_row(instance))
    print("Initialized %s" % store.root)
    return 0


def cmd_init_atr(args) -> int:
    store = _store(args)
    store.ensure()
    config = {
        "signal_tf": args.signal_tf,
        "atr_len": args.atr_len,
        "atr_mult": args.atr_mult,
        "initial_qty": args.initial_qty,
        "add_qty": args.add_qty,
        "max_contracts": args.max_contracts,
        "add_interval": args.add_interval,
        "schedule": args.schedule,
        "use_entry_guard": not args.disable_entry_guard,
        "daily_use_weekly_flat": args.daily_use_weekly_flat,
        "add_on_friday_close": not args.disable_add_on_friday_close,
    }
    instance = StrategyInstance(
        strategy_id=args.strategy_id,
        strategy_type="atr_supertrend_dca",
        version="v1",
        instrument=args.instrument,
        broker_instrument=args.broker_instrument or args.instrument,
        account_mode=args.account_mode,
        enabled=True,
        timeframes="D",
        max_contracts=args.max_contracts,
        max_open_orders=64,
        config_json=json.dumps(config, sort_keys=True),
    )
    store.upsert_row("strategy_instances", "strategy_id", as_row(instance))
    print("Initialized ATR Supertrend DCA %s in %s" % (args.strategy_id, store.root))
    return 0


def cmd_replay(args) -> int:
    store = _store(args)
    engine = Engine(store=store)
    bars = bars_from_csv(Path(args.bars), args.instrument, args.timeframe, source=args.bars)
    engine.replay_bars(bars)
    print("Replayed %d %s bars for %s" % (len(bars), args.timeframe, args.instrument))
    return 0


def cmd_run_once(args) -> int:
    engine = Engine(store=_store(args))
    n = engine.run_pending_jobs(limit=args.limit)
    print("Processed %d jobs" % n)
    return 0


def cmd_report(args) -> int:
    text = generate_market_close_report(_store(args), args.report_date)
    print(text)
    return 0


def cmd_health(args) -> int:
    HealthServer(_store(args), host=args.host, port=args.port).serve_forever()
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Potions flat-file live runtime")
    p.add_argument("--state-root", default=str(default_state_root()))
    sub = p.add_subparsers(dest="cmd", required=True)

    init = sub.add_parser("init", help="Create flat-file runtime state")
    init.add_argument("--with-yearly-orb", action="store_true")
    init.add_argument("--strategy-id", default="yearly_orb_mnq_paper")
    init.add_argument("--instrument", default="MNQ")
    init.add_argument("--broker-instrument", default="")
    init.add_argument("--account-mode", default="paper", choices=["paper", "live"])
    init.add_argument("--batch-qty", type=int, default=1)
    init.add_argument("--max-contracts", type=int, default=3)
    init.set_defaults(func=cmd_init)

    init_atr = sub.add_parser("init-atr", help="Create an ATR Supertrend DCA strategy instance")
    init_atr.add_argument("--strategy-id", default="atr_supertrend_mnq_paper")
    init_atr.add_argument("--instrument", default="MNQ")
    init_atr.add_argument("--broker-instrument", default="")
    init_atr.add_argument("--account-mode", default="paper", choices=["paper", "live"])
    init_atr.add_argument("--signal-tf", default="weekly", choices=["daily", "weekly"])
    init_atr.add_argument("--atr-len", type=int, default=14)
    init_atr.add_argument("--atr-mult", type=float, default=3.0)
    init_atr.add_argument("--initial-qty", type=int, default=3)
    init_atr.add_argument("--add-qty", type=int, default=1)
    init_atr.add_argument("--max-contracts", type=int, default=10)
    init_atr.add_argument("--add-interval", type=int, default=2)
    init_atr.add_argument("--schedule", default="fixed", choices=["fixed", "ladder112221"])
    init_atr.add_argument("--disable-entry-guard", action="store_true")
    init_atr.add_argument("--daily-use-weekly-flat", action="store_true")
    init_atr.add_argument("--disable-add-on-friday-close", action="store_true")
    init_atr.set_defaults(func=cmd_init_atr)

    replay = sub.add_parser("replay", help="Replay completed bars through the paper runtime")
    replay.add_argument("--bars", required=True)
    replay.add_argument("--instrument", required=True)
    replay.add_argument("--timeframe", default="D")
    replay.set_defaults(func=cmd_replay)

    run_once = sub.add_parser("run-once", help="Process pending flat-file jobs")
    run_once.add_argument("--limit", type=int, default=100)
    run_once.set_defaults(func=cmd_run_once)

    report = sub.add_parser("report", help="Generate market-close report")
    report.add_argument("--report-date", default="")
    report.set_defaults(func=cmd_report)

    health = sub.add_parser("health", help="Run local health endpoint")
    health.add_argument("--host", default="127.0.0.1")
    health.add_argument("--port", type=int, default=8765)
    health.set_defaults(func=cmd_health)
    return p


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
