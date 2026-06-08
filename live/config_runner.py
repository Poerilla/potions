from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from threading import Thread
from typing import Any, Dict, Tuple

from .engine import Engine
from .health import HealthServer
from .models import StrategyInstance, as_row, utc_now_iso
from .store import FlatFileStore


REPO_ROOT = Path(__file__).resolve().parents[1]


STRATEGY_ALIASES = {
    "v2b": "v2b_scaleout",
    "v2b_scaleout": "v2b_scaleout",
    "yearly_orb": "yearly_orb_scaleout3",
    "yearly_orb_scaleout3": "yearly_orb_scaleout3",
    "atr_supertrend": "atr_supertrend_dca",
    "atr_supertrend_dca": "atr_supertrend_dca",
}


def load_engine_config(path: Path) -> Dict[str, Any]:
    path = Path(path)
    with path.open("r", encoding="utf-8") as fh:
        config = json.load(fh)
    if not isinstance(config, dict):
        raise ValueError("Engine config must be a JSON object")
    return config


def resolve_state_root(config: Dict[str, Any]) -> Path:
    runtime = config.get("runtime") or {}
    raw = runtime.get("state_root") or "live/state/deploy/default"
    path = Path(str(raw))
    if path.is_absolute():
        return path
    return REPO_ROOT / path


def validate_engine_config(config: Dict[str, Any]) -> None:
    strategy = config.get("strategy") or {}
    if not strategy:
        raise ValueError("Missing strategy section")
    strategy_type = _strategy_type(strategy)
    if strategy_type not in STRATEGY_ALIASES.values():
        raise ValueError("Unsupported strategy_type/model: %s" % strategy_type)

    broker = config.get("broker") or {}
    broker_mode = str(broker.get("mode") or strategy.get("account_mode") or "paper")
    broker_provider = str(broker.get("provider") or "paper")
    if bool(broker.get("allow_live_routing")):
        raise ValueError("allow_live_routing=true is not permitted by this bootstrap runner")
    if broker_mode not in {"paper", "sim"} or broker_provider not in {"paper", "local"}:
        raise NotImplementedError(
            "Only the local PaperBroker is wired here. Requested provider=%s mode=%s"
            % (broker_provider, broker_mode)
        )


def build_strategy_instance(config: Dict[str, Any]) -> StrategyInstance:
    validate_engine_config(config)
    strategy = config.get("strategy") or {}
    strategy_type = _strategy_type(strategy)
    strategy_config = strategy.get("config_json", strategy.get("config", {}))
    if isinstance(strategy_config, str):
        strategy_config = json.loads(strategy_config or "{}")
    if not isinstance(strategy_config, dict):
        raise ValueError("strategy.config must be an object")

    account_mode = str(strategy.get("account_mode") or (config.get("broker") or {}).get("mode") or "paper")
    if account_mode == "sim":
        account_mode = "paper"

    max_contracts = int(strategy.get("max_contracts") or strategy_config.get("entry_qty") or 1)
    return StrategyInstance(
        strategy_id=str(strategy.get("strategy_id") or "mnq_v2b_1_0_0_demo"),
        strategy_type=strategy_type,
        version=str(strategy.get("version") or "v1"),
        instrument=str(strategy.get("instrument") or "MNQ"),
        broker_instrument=str(strategy.get("broker_instrument") or strategy.get("instrument") or "MNQ"),
        account_mode=account_mode,
        enabled=bool(strategy.get("enabled", True)),
        timeframes=str(strategy.get("timeframes") or strategy.get("timeframe") or "1m"),
        max_contracts=max_contracts,
        max_open_orders=int(strategy.get("max_open_orders") or 12),
        config_json=json.dumps(strategy_config, sort_keys=True),
    )


def init_from_config(config_path: Path) -> Tuple[Path, StrategyInstance]:
    config = load_engine_config(config_path)
    store = FlatFileStore(resolve_state_root(config))
    store.ensure()
    instance = build_strategy_instance(config)
    store.upsert_row("strategy_instances", "strategy_id", as_row(instance))
    store.write_json(
        "runtime_config.json",
        {
            "config_path": str(Path(config_path).resolve()),
            "strategy_id": instance.strategy_id,
            "strategy_type": instance.strategy_type,
            "instrument": instance.instrument,
            "broker_instrument": instance.broker_instrument,
            "account_mode": instance.account_mode,
            "updated_at": utc_now_iso(),
        },
    )
    return store.root, instance


def run_loop_from_config(config_path: Path) -> None:
    config = load_engine_config(config_path)
    root, instance = init_from_config(config_path)
    store = FlatFileStore(root)
    _start_health_if_enabled(config, store)

    runtime = config.get("runtime") or {}
    poll_seconds = float(runtime.get("poll_seconds") or 1.0)
    engine = Engine(store=store)
    engine.manager.startup_reconcile()
    store.write_json(
        "health.json",
        {
            "status": "ok",
            "strategy_id": instance.strategy_id,
            "mode": "paper",
            "updated_at": utc_now_iso(),
        },
    )
    while True:
        processed = engine.run_pending_jobs(limit=int(runtime.get("job_limit") or 100))
        store.write_json(
            "health.json",
            {
                "status": "ok",
                "strategy_id": instance.strategy_id,
                "mode": "paper",
                "last_jobs_processed": processed,
                "updated_at": utc_now_iso(),
            },
        )
        time.sleep(poll_seconds)


def _strategy_type(strategy: Dict[str, Any]) -> str:
    raw = str(strategy.get("strategy_type") or strategy.get("model") or "").strip()
    if not raw:
        raise ValueError("strategy.strategy_type or strategy.model is required")
    return STRATEGY_ALIASES.get(raw, raw)


def _start_health_if_enabled(config: Dict[str, Any], store: FlatFileStore) -> None:
    health = (config.get("runtime") or {}).get("health") or {}
    if not bool(health.get("enabled", False)):
        return
    host = str(health.get("host") or "127.0.0.1")
    port = int(health.get("port") or 8765)
    thread = Thread(target=HealthServer(store, host=host, port=port).serve_forever, daemon=True)
    thread.start()


def cmd_check(args) -> int:
    config = load_engine_config(Path(args.config))
    instance = build_strategy_instance(config)
    summary = {
        "state_root": str(resolve_state_root(config)),
        "strategy_id": instance.strategy_id,
        "strategy_type": instance.strategy_type,
        "instrument": instance.instrument,
        "broker_instrument": instance.broker_instrument,
        "account_mode": instance.account_mode,
        "timeframes": instance.timeframes,
        "max_contracts": instance.max_contracts,
        "max_open_orders": instance.max_open_orders,
        "config": json.loads(instance.config_json),
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


def cmd_init(args) -> int:
    root, instance = init_from_config(Path(args.config))
    print("Initialized %s at %s" % (instance.strategy_id, root))
    return 0


def cmd_run_loop(args) -> int:
    run_loop_from_config(Path(args.config))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a live Engine config")
    parser.add_argument("--config", required=True, help="Path to engine.conf JSON")
    sub = parser.add_subparsers(dest="cmd", required=True)
    check = sub.add_parser("check", help="Validate and summarize config")
    check.set_defaults(func=cmd_check)
    init = sub.add_parser("init", help="Initialize flat-file runtime state from config")
    init.set_defaults(func=cmd_init)
    run_loop = sub.add_parser("run-loop", help="Run the local paper Engine job loop")
    run_loop.set_defaults(func=cmd_run_loop)
    return parser


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
