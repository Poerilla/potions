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


def _cqg_config(args):
    from .cqg import CqgWebApiConfig

    if getattr(args, "cqg_config", ""):
        return CqgWebApiConfig.from_json_file(Path(args.cqg_config))
    return CqgWebApiConfig.from_env()


def _tradovate_config(args):
    from .tradovate import TradovateConfig

    if getattr(args, "tradovate_config", ""):
        return TradovateConfig.from_json_file(Path(args.tradovate_config))
    return TradovateConfig.from_env()


def _oanda_config(args):
    from .oanda import OandaConfig

    if getattr(args, "oanda_config", ""):
        return OandaConfig.from_json_file(Path(args.oanda_config))
    return OandaConfig.from_env()


def cmd_tradovate_smoke(args) -> int:
    from .tradovate import (
        DEFAULT_INSTRUMENTS,
        TradovateMarketDataFeedAdapter,
        TradovateOpenApiCatalog,
        TradovateWebApiClient,
    )

    store = _store(args)
    store.ensure()
    config = _tradovate_config(args)
    catalog = TradovateOpenApiCatalog.load(config.openapi_path)
    catalog.validate_required_routes()
    client = TradovateWebApiClient(config=config, store=store, catalog=catalog)
    instruments = [item.strip().upper() for item in (args.instruments or ",".join(DEFAULT_INSTRUMENTS)).split(",") if item.strip()]
    store.append_event(
        "tradovate_session_events",
        {
            "event": "smoke_start",
            "offline": bool(args.offline),
            "env": config.env,
            "rest_endpoint": config.rest_endpoint,
            "ws_endpoint": config.ws_endpoint,
            "md_ws_endpoint": config.md_ws_endpoint,
            "instruments": ",".join(instruments),
            "openapi_path": str(catalog.path),
        },
    )
    auth_body = client.build_access_token_body()
    frames = [
        client.build_authorize_frame("<access_token>", request_id=1),
        client.build_user_sync_frame(request_id=2),
    ]
    adapter = TradovateMarketDataFeedAdapter(store, config=config)
    for idx, instrument in enumerate(instruments, start=1):
        symbol = config.symbol_for(instrument)
        adapter.resolve_contract(instrument, str(args.contract_id or symbol), symbol=symbol, metadata={"smoke": True})
        frames.append(client.build_contract_roll_frame(symbol, request_id=10 + idx))
    if args.offline:
        store.append_event(
            "tradovate_session_events",
            {
                "event": "smoke_offline_ok",
                "auth_fields": ",".join(sorted(auth_body)),
                "frames_built": len(frames),
                "required_routes": len(catalog.spec.get("paths") or {}),
            },
        )
        print(
            "Tradovate offline smoke ok: env=%s endpoint=%s instruments=%s openapi=%s"
            % (config.env, config.rest_endpoint, ",".join(instruments), catalog.path)
        )
        return 0

    token = client.request_access_token()
    client.renew_access_token(token.access_token)
    accounts = client.request_json("GET", "/account/list", None, token.access_token)
    store.append_event(
        "tradovate_session_events",
        {
            "event": "smoke_network_ok",
            "user_id": token.user_id,
            "account_count": len(accounts) if isinstance(accounts, list) else "",
            "frames_built": len(frames),
        },
    )
    print("Tradovate network smoke ok: user_id=%s account_payload_type=%s" % (token.user_id, type(accounts).__name__))
    return 0


def cmd_tradovate_feed_shadow(args) -> int:
    from .tradovate import TradovateMarketDataFeedAdapter, load_jsonl_events

    if not args.events:
        raise SystemExit("tradovate-feed-shadow requires --events JSONL for offline replay")
    store = _store(args)
    adapter = TradovateMarketDataFeedAdapter(store, config=_tradovate_config(args))
    count = 0
    emitted = 0
    for event in load_jsonl_events(Path(args.events)):
        count += 1
        emitted += len(adapter.on_raw_event(event))
    emitted += len(adapter.flush())
    health = adapter.health()
    print(
        "Tradovate feed shadow replayed %d events, emitted %d bars, status=%s reason=%s"
        % (count, emitted, health.status, adapter.blocking_reason() or "none")
    )
    return 0


def cmd_tradovate_paper(args) -> int:
    from .supervisor import RuntimeSupervisor
    from .tradovate import TradovateBroker, TradovateMarketDataFeedAdapter, load_jsonl_events

    store = _store(args)
    config = _tradovate_config(args)
    supervisor = RuntimeSupervisor(store, provider="tradovate")
    broker = TradovateBroker(
        store,
        config=config,
        allow_live_routing=False,
        server_oco_validated=bool(args.server_oco_validated),
        supervisor=supervisor,
    )
    adapter = TradovateMarketDataFeedAdapter(store, config=config, supervisor=supervisor)
    count = 0
    emitted = 0
    if args.events:
        for event in load_jsonl_events(Path(args.events)):
            count += 1
            event_type = str(event.get("type") or event.get("event") or "")
            if event_type == "order_status":
                broker.on_order_status(event)
            elif event_type == "fill":
                broker.on_fill(event)
            else:
                emitted += len(adapter.on_raw_event(event))
        emitted += len(adapter.flush())
    store.append_event(
        "tradovate_session_events",
        {
            "event": "tradovate_paper_ready",
            "events_replayed": count,
            "bars_emitted": emitted,
            "active_orders": len(broker.reconcile_orders()),
            "positions": len(broker.reconcile_positions()),
            "server_oco_validated": bool(args.server_oco_validated),
        },
    )
    print(
        "Tradovate paper scaffold ready: replayed %d events, emitted %d bars, active_orders=%d"
        % (count, emitted, len(broker.reconcile_orders()))
    )
    return 0


def cmd_tradovate_emergency_flatten(args) -> int:
    from .supervisor import RuntimeSupervisor
    from .tradovate import DEFAULT_INSTRUMENTS, TradovateBroker

    store = _store(args)
    config = _tradovate_config(args)
    supervisor = RuntimeSupervisor(store, provider="tradovate")
    broker = TradovateBroker(store, config=config, allow_live_routing=bool(args.allow_live), supervisor=supervisor)
    instruments = [item.strip().upper() for item in (args.instruments or ",".join(DEFAULT_INSTRUMENTS)).split(",") if item.strip()]
    payloads = broker.go_flat(instruments=instruments)
    print("Tradovate emergency flatten requested for %s (%d liquidation payloads)" % (",".join(instruments), len(payloads)))
    return 0


def cmd_oanda_smoke(args) -> int:
    from .oanda import DEFAULT_INSTRUMENTS, OandaApiClient, OandaMarketDataFeedAdapter

    store = _store(args)
    store.ensure()
    config = _oanda_config(args)
    instruments = [item.strip().upper() for item in (args.instruments or ",".join(DEFAULT_INSTRUMENTS)).split(",") if item.strip()]
    store.append_event(
        "oanda_session_events",
        {
            "event": "smoke_start",
            "offline": bool(args.offline),
            "env": config.env,
            "api_url": config.api_url,
            "stream_url": config.stream_url,
            "account_id": config.account_id,
            "instruments": ",".join(instruments),
        },
    )
    adapter = OandaMarketDataFeedAdapter(store, config=config)
    for instrument in instruments:
        adapter.resolve_instrument(instrument)
    if args.offline:
        client = OandaApiClient(config=config, store=store, context=object())
        store.append_event(
            "oanda_session_events",
            {
                "event": "smoke_offline_ok",
                "mapped": {inst: config.symbol_for(inst) for inst in instruments},
                "hostname": config.hostname(),
                "client_ready": client is not None,
            },
        )
        print(
            "OANDA offline smoke ok: env=%s api=%s account=%s instruments=%s"
            % (config.env, config.api_url, config.account_id, ",".join("%s=%s" % (i, config.symbol_for(i)) for i in instruments))
        )
        return 0

    config.validate_for_network()
    client = OandaApiClient(config=config, store=store)
    details = client.account_details()
    instruments_body = client.account_instruments()
    prices = client.pricing_get([config.symbol_for(i) for i in instruments])
    price_count = len(prices.get("prices") or [])
    store.append_event(
        "oanda_session_events",
        {
            "event": "smoke_network_ok",
            "last_transaction_id": client.last_transaction_id,
            "price_count": price_count,
            "instrument_count": len(instruments_body.get("instruments") or []),
            "has_account": bool(details.get("account")),
        },
    )
    print(
        "OANDA network smoke ok: account=%s lastTransactionID=%s prices=%d"
        % (config.account_id, client.last_transaction_id, price_count)
    )
    return 0


def cmd_oanda_stream_prices(args) -> int:
    """Print live OANDA bid/ask ticks to the console until Ctrl-C or --max-ticks."""
    from .oanda import DEFAULT_INSTRUMENTS, OandaApiClient

    store = _store(args)
    store.ensure()
    config = _oanda_config(args)
    config.validate_for_network()
    roots = [item.strip().upper() for item in (args.instruments or ",".join(DEFAULT_INSTRUMENTS)).split(",") if item.strip()]
    oanda_names = [config.symbol_for(root) for root in roots]
    client = OandaApiClient(config=config, store=store)
    print(
        "Streaming %s on %s (account=%s). Ctrl-C to stop."
        % (",".join(oanda_names), config.stream_hostname(), config.account_id),
        flush=True,
    )
    response = client.pricing_stream(oanda_names, snapshot=not bool(args.no_snapshot))
    status = int(getattr(response, "status", 0) or 0)
    if status != 200:
        raise SystemExit("pricing stream failed: status=%s reason=%s" % (response.status, getattr(response, "reason", "")))
    count = 0
    try:
        for msg_type, msg in response.parts():
            if msg_type == "pricing.PricingHeartbeat" or getattr(msg, "type", None) == "HEARTBEAT":
                if args.heartbeats:
                    print("HEARTBEAT %s" % getattr(msg, "time", ""), flush=True)
                continue
            instrument = getattr(msg, "instrument", "") or ""
            time_s = getattr(msg, "time", "") or ""
            bids = getattr(msg, "bids", None) or []
            asks = getattr(msg, "asks", None) or []
            bid = bids[0].price if bids else ""
            ask = asks[0].price if asks else ""
            mid = ""
            try:
                if bid != "" and ask != "":
                    mid = "%.6f" % ((float(bid) + float(ask)) / 2.0)
            except (TypeError, ValueError):
                mid = ""
            print("%s  %s  bid=%s  ask=%s  mid=%s" % (time_s, instrument, bid, ask, mid), flush=True)
            count += 1
            if args.max_ticks and count >= int(args.max_ticks):
                break
    except KeyboardInterrupt:
        print("\nStopped after %d ticks." % count, flush=True)
        return 0
    print("Done (%d ticks)." % count, flush=True)
    return 0


def cmd_oanda_feed_shadow(args) -> int:
    from .oanda import OandaMarketDataFeedAdapter, load_jsonl_events

    if not args.events:
        raise SystemExit("oanda-feed-shadow requires --events JSONL for offline replay")
    store = _store(args)
    adapter = OandaMarketDataFeedAdapter(store, config=_oanda_config(args))
    count = 0
    emitted = 0
    for event in load_jsonl_events(Path(args.events)):
        count += 1
        emitted += len(adapter.on_raw_event(event))
    emitted += len(adapter.flush())
    health = adapter.health()
    print(
        "OANDA feed shadow replayed %d events, emitted %d bars, status=%s reason=%s"
        % (count, emitted, health.status, adapter.blocking_reason() or "none")
    )
    return 0


def cmd_oanda_paper(args) -> int:
    from .supervisor import RuntimeSupervisor
    from .oanda import OandaBroker, OandaMarketDataFeedAdapter, load_jsonl_events

    store = _store(args)
    config = _oanda_config(args)
    supervisor = RuntimeSupervisor(store, provider="oanda")
    broker = OandaBroker(store, config=config, allow_live_routing=False, supervisor=supervisor)
    adapter = OandaMarketDataFeedAdapter(store, config=config, supervisor=supervisor)
    count = 0
    emitted = 0
    if args.events:
        for event in load_jsonl_events(Path(args.events)):
            count += 1
            event_type = str(event.get("type") or event.get("event") or "")
            if event_type == "order_status":
                broker.on_order_status(event)
            elif event_type == "fill":
                broker.on_fill(event)
            elif event_type == "account_changes":
                broker.apply_account_changes(event)
            else:
                emitted += len(adapter.on_raw_event(event))
        emitted += len(adapter.flush())
    store.append_event(
        "oanda_session_events",
        {
            "event": "oanda_paper_ready",
            "events_replayed": count,
            "bars_emitted": emitted,
            "active_orders": len(broker.reconcile_orders()),
            "positions": len(broker.reconcile_positions()),
        },
    )
    print(
        "OANDA paper scaffold ready: replayed %d events, emitted %d bars, active_orders=%d"
        % (count, emitted, len(broker.reconcile_orders()))
    )
    return 0


def cmd_oanda_emergency_flatten(args) -> int:
    from .supervisor import RuntimeSupervisor
    from .oanda import DEFAULT_INSTRUMENTS, OandaBroker

    store = _store(args)
    config = _oanda_config(args)
    supervisor = RuntimeSupervisor(store, provider="oanda")
    broker = OandaBroker(store, config=config, allow_live_routing=bool(args.allow_live), supervisor=supervisor)
    instruments = [item.strip().upper() for item in (args.instruments or ",".join(DEFAULT_INSTRUMENTS)).split(",") if item.strip()]
    payloads = broker.go_flat(instruments=instruments)
    print("OANDA emergency flatten requested for %s (%d close payloads)" % (",".join(instruments), len(payloads)))
    return 0


def _demo_output_root(args) -> Path:
    from .demo.eurusd_v2b_ungated_paper import default_output_root

    if getattr(args, "output_root", ""):
        return Path(args.output_root)
    return default_output_root()


def _demo_nas100_output_root(args) -> Path:
    from .demo.nas100_v2b_ungated_paper import default_output_root

    if getattr(args, "output_root", ""):
        return Path(args.output_root)
    return default_output_root()


def cmd_demo_eurusd_v2b_paper(args) -> int:
    from .demo.eurusd_v2b_ungated_paper import run_stream_loop, spawn_daemon
    from .oanda import OandaConfig

    output_root = _demo_output_root(args)
    if args.daemon:
        return spawn_daemon(
            output_root=output_root,
            max_ticks=int(args.max_ticks or 0),
            oanda_config_path=getattr(args, "oanda_config", "") or "",
        )
    config = OandaConfig.from_json_file(Path(args.oanda_config)) if getattr(args, "oanda_config", "") else OandaConfig.from_env()
    return run_stream_loop(output_root=output_root, config=config, max_ticks=int(args.max_ticks or 0))


def cmd_demo_eurusd_v2b_paper_status(args) -> int:
    from .demo.eurusd_v2b_ungated_paper import status_daemon

    return status_daemon(_demo_output_root(args))


def cmd_demo_eurusd_v2b_paper_stop(args) -> int:
    from .demo.eurusd_v2b_ungated_paper import stop_daemon

    return stop_daemon(_demo_output_root(args))


def cmd_demo_nas100_v2b_paper(args) -> int:
    from .demo.nas100_v2b_ungated_paper import run_stream_loop, spawn_daemon
    from .oanda import OandaConfig

    output_root = _demo_nas100_output_root(args)
    if args.daemon:
        return spawn_daemon(
            output_root=output_root,
            max_ticks=int(args.max_ticks or 0),
            oanda_config_path=getattr(args, "oanda_config", "") or "",
        )
    config = OandaConfig.from_json_file(Path(args.oanda_config)) if getattr(args, "oanda_config", "") else OandaConfig.from_env()
    return run_stream_loop(output_root=output_root, config=config, max_ticks=int(args.max_ticks or 0))


def cmd_demo_nas100_v2b_paper_status(args) -> int:
    from .demo.nas100_v2b_ungated_paper import status_daemon

    return status_daemon(_demo_nas100_output_root(args))


def cmd_demo_nas100_v2b_paper_stop(args) -> int:
    from .demo.nas100_v2b_ungated_paper import stop_daemon

    return stop_daemon(_demo_nas100_output_root(args))


def _demo_spx500_output_root(args) -> Path:
    from .demo.spx500_v2b_ungated_paper import default_output_root

    if getattr(args, "output_root", ""):
        return Path(args.output_root)
    return default_output_root()


def _demo_us30_output_root(args) -> Path:
    from .demo.us30_v2b_ungated_paper import default_output_root

    if getattr(args, "output_root", ""):
        return Path(args.output_root)
    return default_output_root()


def cmd_demo_spx500_v2b_paper(args) -> int:
    from .demo.spx500_v2b_ungated_paper import run_stream_loop, spawn_daemon
    from .oanda import OandaConfig

    output_root = _demo_spx500_output_root(args)
    if args.daemon:
        return spawn_daemon(
            output_root=output_root,
            max_ticks=int(args.max_ticks or 0),
            oanda_config_path=getattr(args, "oanda_config", "") or "",
        )
    config = OandaConfig.from_json_file(Path(args.oanda_config)) if getattr(args, "oanda_config", "") else OandaConfig.from_env()
    return run_stream_loop(output_root=output_root, config=config, max_ticks=int(args.max_ticks or 0))


def cmd_demo_spx500_v2b_paper_status(args) -> int:
    from .demo.spx500_v2b_ungated_paper import status_daemon

    return status_daemon(_demo_spx500_output_root(args))


def cmd_demo_spx500_v2b_paper_stop(args) -> int:
    from .demo.spx500_v2b_ungated_paper import stop_daemon

    return stop_daemon(_demo_spx500_output_root(args))


def cmd_demo_us30_v2b_paper(args) -> int:
    from .demo.us30_v2b_ungated_paper import run_stream_loop, spawn_daemon
    from .oanda import OandaConfig

    output_root = _demo_us30_output_root(args)
    if args.daemon:
        return spawn_daemon(
            output_root=output_root,
            max_ticks=int(args.max_ticks or 0),
            oanda_config_path=getattr(args, "oanda_config", "") or "",
        )
    config = OandaConfig.from_json_file(Path(args.oanda_config)) if getattr(args, "oanda_config", "") else OandaConfig.from_env()
    return run_stream_loop(output_root=output_root, config=config, max_ticks=int(args.max_ticks or 0))


def cmd_demo_us30_v2b_paper_status(args) -> int:
    from .demo.us30_v2b_ungated_paper import status_daemon

    return status_daemon(_demo_us30_output_root(args))


def cmd_demo_us30_v2b_paper_stop(args) -> int:
    from .demo.us30_v2b_ungated_paper import stop_daemon

    return stop_daemon(_demo_us30_output_root(args))


def _demo_eurusd_oanda_output_root(args) -> Path:
    from .demo.eurusd_v2b_ungated_oanda import default_output_root

    if getattr(args, "output_root", ""):
        return Path(args.output_root)
    return default_output_root()


def _demo_nas100_oanda_output_root(args) -> Path:
    from .demo.nas100_v2b_ungated_oanda import default_output_root

    if getattr(args, "output_root", ""):
        return Path(args.output_root)
    return default_output_root()


def _demo_spx500_oanda_output_root(args) -> Path:
    from .demo.spx500_v2b_ungated_oanda import default_output_root

    if getattr(args, "output_root", ""):
        return Path(args.output_root)
    return default_output_root()


def _demo_us30_oanda_output_root(args) -> Path:
    from .demo.us30_v2b_ungated_oanda import default_output_root

    if getattr(args, "output_root", ""):
        return Path(args.output_root)
    return default_output_root()


def cmd_demo_eurusd_v2b_oanda(args) -> int:
    from .demo.eurusd_v2b_ungated_oanda import run_stream_loop, spawn_daemon
    from .oanda import OandaConfig

    output_root = _demo_eurusd_oanda_output_root(args)
    if args.daemon:
        return spawn_daemon(
            output_root=output_root,
            max_ticks=int(args.max_ticks or 0),
            oanda_config_path=getattr(args, "oanda_config", "") or "",
        )
    config = OandaConfig.from_json_file(Path(args.oanda_config)) if getattr(args, "oanda_config", "") else OandaConfig.from_env()
    return run_stream_loop(output_root=output_root, config=config, max_ticks=int(args.max_ticks or 0))


def cmd_demo_eurusd_v2b_oanda_status(args) -> int:
    from .demo.eurusd_v2b_ungated_oanda import status_daemon

    return status_daemon(_demo_eurusd_oanda_output_root(args))


def cmd_demo_eurusd_v2b_oanda_stop(args) -> int:
    from .demo.eurusd_v2b_ungated_oanda import stop_daemon

    return stop_daemon(_demo_eurusd_oanda_output_root(args))


def cmd_demo_nas100_v2b_oanda(args) -> int:
    from .demo.nas100_v2b_ungated_oanda import run_stream_loop, spawn_daemon
    from .oanda import OandaConfig

    output_root = _demo_nas100_oanda_output_root(args)
    if args.daemon:
        return spawn_daemon(
            output_root=output_root,
            max_ticks=int(args.max_ticks or 0),
            oanda_config_path=getattr(args, "oanda_config", "") or "",
        )
    config = OandaConfig.from_json_file(Path(args.oanda_config)) if getattr(args, "oanda_config", "") else OandaConfig.from_env()
    return run_stream_loop(output_root=output_root, config=config, max_ticks=int(args.max_ticks or 0))


def cmd_demo_nas100_v2b_oanda_status(args) -> int:
    from .demo.nas100_v2b_ungated_oanda import status_daemon

    return status_daemon(_demo_nas100_oanda_output_root(args))


def cmd_demo_nas100_v2b_oanda_stop(args) -> int:
    from .demo.nas100_v2b_ungated_oanda import stop_daemon

    return stop_daemon(_demo_nas100_oanda_output_root(args))


def cmd_demo_spx500_v2b_oanda(args) -> int:
    from .demo.spx500_v2b_ungated_oanda import run_stream_loop, spawn_daemon
    from .oanda import OandaConfig

    output_root = _demo_spx500_oanda_output_root(args)
    if args.daemon:
        return spawn_daemon(
            output_root=output_root,
            max_ticks=int(args.max_ticks or 0),
            oanda_config_path=getattr(args, "oanda_config", "") or "",
        )
    config = OandaConfig.from_json_file(Path(args.oanda_config)) if getattr(args, "oanda_config", "") else OandaConfig.from_env()
    return run_stream_loop(output_root=output_root, config=config, max_ticks=int(args.max_ticks or 0))


def cmd_demo_spx500_v2b_oanda_status(args) -> int:
    from .demo.spx500_v2b_ungated_oanda import status_daemon

    return status_daemon(_demo_spx500_oanda_output_root(args))


def cmd_demo_spx500_v2b_oanda_stop(args) -> int:
    from .demo.spx500_v2b_ungated_oanda import stop_daemon

    return stop_daemon(_demo_spx500_oanda_output_root(args))


def cmd_demo_us30_v2b_oanda(args) -> int:
    from .demo.us30_v2b_ungated_oanda import run_stream_loop, spawn_daemon
    from .oanda import OandaConfig

    output_root = _demo_us30_oanda_output_root(args)
    if args.daemon:
        return spawn_daemon(
            output_root=output_root,
            max_ticks=int(args.max_ticks or 0),
            oanda_config_path=getattr(args, "oanda_config", "") or "",
        )
    config = OandaConfig.from_json_file(Path(args.oanda_config)) if getattr(args, "oanda_config", "") else OandaConfig.from_env()
    return run_stream_loop(output_root=output_root, config=config, max_ticks=int(args.max_ticks or 0))


def cmd_demo_us30_v2b_oanda_status(args) -> int:
    from .demo.us30_v2b_ungated_oanda import status_daemon

    return status_daemon(_demo_us30_oanda_output_root(args))


def cmd_demo_us30_v2b_oanda_stop(args) -> int:
    from .demo.us30_v2b_ungated_oanda import stop_daemon

    return stop_daemon(_demo_us30_oanda_output_root(args))


def _demo_usdjpy_monday_or_oanda_output_root(args) -> Path:
    from .demo.usdjpy_monday_or_ungated_oanda import default_output_root

    if getattr(args, "output_root", ""):
        return Path(args.output_root)
    return default_output_root()


def cmd_demo_usdjpy_monday_or_oanda(args) -> int:
    from .demo.usdjpy_monday_or_ungated_oanda import run_stream_loop, spawn_daemon
    from .oanda import OandaConfig

    output_root = _demo_usdjpy_monday_or_oanda_output_root(args)
    if args.daemon:
        return spawn_daemon(
            output_root=output_root,
            max_ticks=int(args.max_ticks or 0),
            oanda_config_path=getattr(args, "oanda_config", "") or "",
        )
    config = OandaConfig.from_json_file(Path(args.oanda_config)) if getattr(args, "oanda_config", "") else OandaConfig.from_env()
    return run_stream_loop(output_root=output_root, config=config, max_ticks=int(args.max_ticks or 0))


def cmd_demo_usdjpy_monday_or_oanda_status(args) -> int:
    from .demo.usdjpy_monday_or_ungated_oanda import status_daemon

    return status_daemon(_demo_usdjpy_monday_or_oanda_output_root(args))


def cmd_demo_usdjpy_monday_or_oanda_stop(args) -> int:
    from .demo.usdjpy_monday_or_ungated_oanda import stop_daemon

    return stop_daemon(_demo_usdjpy_monday_or_oanda_output_root(args))


def _demo_usdjpy_monday_or_paper_output_root(args) -> Path:
    from .demo.usdjpy_monday_or_ungated_paper import default_output_root

    return Path(args.output_root) if getattr(args, "output_root", "") else default_output_root()


def cmd_demo_usdjpy_monday_or_paper(args) -> int:
    from .demo.usdjpy_monday_or_ungated_paper import run_stream_loop, spawn_daemon
    from .oanda import OandaConfig

    output_root = _demo_usdjpy_monday_or_paper_output_root(args)
    if args.daemon:
        return spawn_daemon(
            output_root=output_root,
            max_ticks=int(args.max_ticks or 0),
            oanda_config_path=getattr(args, "oanda_config", "") or "",
        )
    config = OandaConfig.from_json_file(Path(args.oanda_config)) if getattr(args, "oanda_config", "") else OandaConfig.from_env()
    return run_stream_loop(output_root=output_root, config=config, max_ticks=int(args.max_ticks or 0))


def cmd_demo_usdjpy_monday_or_paper_status(args) -> int:
    from .demo.usdjpy_monday_or_ungated_paper import status_daemon

    return status_daemon(_demo_usdjpy_monday_or_paper_output_root(args))


def cmd_demo_usdjpy_monday_or_paper_stop(args) -> int:
    from .demo.usdjpy_monday_or_ungated_paper import stop_daemon

    return stop_daemon(_demo_usdjpy_monday_or_paper_output_root(args))




def _demo_eurusd_st_pmc_paper_output_root(args) -> Path:
    from .demo.eurusd_hourly_st_pmc_paper import default_output_root
    return Path(args.output_root) if getattr(args, "output_root", "") else default_output_root()


def cmd_demo_eurusd_hourly_st_pmc_paper(args) -> int:
    from .demo.eurusd_hourly_st_pmc_paper import run_stream_loop, spawn_daemon
    from .oanda import OandaConfig
    output_root = _demo_eurusd_st_pmc_paper_output_root(args)
    if args.daemon:
        return spawn_daemon(output_root=output_root, max_ticks=int(args.max_ticks or 0), oanda_config_path=getattr(args, "oanda_config", "") or "")
    config = OandaConfig.from_json_file(Path(args.oanda_config)) if getattr(args, "oanda_config", "") else OandaConfig.from_env()
    return run_stream_loop(output_root=output_root, config=config, max_ticks=int(args.max_ticks or 0))


def cmd_demo_eurusd_hourly_st_pmc_paper_status(args) -> int:
    from .demo.eurusd_hourly_st_pmc_paper import status_daemon
    return status_daemon(_demo_eurusd_st_pmc_paper_output_root(args))


def cmd_demo_eurusd_hourly_st_pmc_paper_stop(args) -> int:
    from .demo.eurusd_hourly_st_pmc_paper import stop_daemon
    return stop_daemon(_demo_eurusd_st_pmc_paper_output_root(args))


def _demo_eurusd_st_pmc_oanda_output_root(args) -> Path:
    from .demo.eurusd_hourly_st_pmc_oanda import default_output_root
    return Path(args.output_root) if getattr(args, "output_root", "") else default_output_root()


def cmd_demo_eurusd_hourly_st_pmc_oanda(args) -> int:
    from .demo.eurusd_hourly_st_pmc_oanda import run_stream_loop, spawn_daemon
    from .oanda import OandaConfig
    output_root = _demo_eurusd_st_pmc_oanda_output_root(args)
    if args.daemon:
        return spawn_daemon(output_root=output_root, max_ticks=int(args.max_ticks or 0), oanda_config_path=getattr(args, "oanda_config", "") or "")
    config = OandaConfig.from_json_file(Path(args.oanda_config)) if getattr(args, "oanda_config", "") else OandaConfig.from_env()
    return run_stream_loop(output_root=output_root, config=config, max_ticks=int(args.max_ticks or 0))


def cmd_demo_eurusd_hourly_st_pmc_oanda_status(args) -> int:
    from .demo.eurusd_hourly_st_pmc_oanda import status_daemon
    return status_daemon(_demo_eurusd_st_pmc_oanda_output_root(args))


def cmd_demo_eurusd_hourly_st_pmc_oanda_stop(args) -> int:
    from .demo.eurusd_hourly_st_pmc_oanda import stop_daemon
    return stop_daemon(_demo_eurusd_st_pmc_oanda_output_root(args))


def _demo_eurusd_st_pmc_2r10r_paper_output_root(args) -> Path:
    from .demo.eurusd_hourly_st_pmc_runners_2r_10r_paper import default_output_root
    return Path(args.output_root) if getattr(args, "output_root", "") else default_output_root()


def cmd_demo_eurusd_hourly_st_pmc_2r10r_paper(args) -> int:
    from .demo.eurusd_hourly_st_pmc_runners_2r_10r_paper import run_stream_loop, spawn_daemon
    from .oanda import OandaConfig
    output_root = _demo_eurusd_st_pmc_2r10r_paper_output_root(args)
    if args.daemon:
        return spawn_daemon(output_root=output_root, max_ticks=int(args.max_ticks or 0), oanda_config_path=getattr(args, "oanda_config", "") or "")
    config = OandaConfig.from_json_file(Path(args.oanda_config)) if getattr(args, "oanda_config", "") else OandaConfig.from_env()
    return run_stream_loop(output_root=output_root, config=config, max_ticks=int(args.max_ticks or 0))


def cmd_demo_eurusd_hourly_st_pmc_2r10r_paper_status(args) -> int:
    from .demo.eurusd_hourly_st_pmc_runners_2r_10r_paper import status_daemon
    return status_daemon(_demo_eurusd_st_pmc_2r10r_paper_output_root(args))


def cmd_demo_eurusd_hourly_st_pmc_2r10r_paper_stop(args) -> int:
    from .demo.eurusd_hourly_st_pmc_runners_2r_10r_paper import stop_daemon
    return stop_daemon(_demo_eurusd_st_pmc_2r10r_paper_output_root(args))


def _demo_eurusd_st_pmc_2r10r_oanda_output_root(args) -> Path:
    from .demo.eurusd_hourly_st_pmc_runners_2r_10r_oanda import default_output_root
    return Path(args.output_root) if getattr(args, "output_root", "") else default_output_root()


def cmd_demo_eurusd_hourly_st_pmc_2r10r_oanda(args) -> int:
    from .demo.eurusd_hourly_st_pmc_runners_2r_10r_oanda import run_stream_loop, spawn_daemon
    from .oanda import OandaConfig
    output_root = _demo_eurusd_st_pmc_2r10r_oanda_output_root(args)
    if args.daemon:
        return spawn_daemon(output_root=output_root, max_ticks=int(args.max_ticks or 0), oanda_config_path=getattr(args, "oanda_config", "") or "")
    config = OandaConfig.from_json_file(Path(args.oanda_config)) if getattr(args, "oanda_config", "") else OandaConfig.from_env()
    return run_stream_loop(output_root=output_root, config=config, max_ticks=int(args.max_ticks or 0))


def cmd_demo_eurusd_hourly_st_pmc_2r10r_oanda_status(args) -> int:
    from .demo.eurusd_hourly_st_pmc_runners_2r_10r_oanda import status_daemon
    return status_daemon(_demo_eurusd_st_pmc_2r10r_oanda_output_root(args))


def cmd_demo_eurusd_hourly_st_pmc_2r10r_oanda_stop(args) -> int:
    from .demo.eurusd_hourly_st_pmc_runners_2r_10r_oanda import stop_daemon
    return stop_daemon(_demo_eurusd_st_pmc_2r10r_oanda_output_root(args))


def _demo_us30_monday_or_paper_output_root(args) -> Path:
    from .demo.us30_monday_or_paper import default_output_root
    return Path(args.output_root) if getattr(args, "output_root", "") else default_output_root()


def cmd_demo_us30_monday_or_paper(args) -> int:
    from .demo.us30_monday_or_paper import run_stream_loop, spawn_daemon
    from .oanda import OandaConfig
    output_root = _demo_us30_monday_or_paper_output_root(args)
    if args.daemon:
        return spawn_daemon(output_root=output_root, max_ticks=int(args.max_ticks or 0), oanda_config_path=getattr(args, "oanda_config", "") or "")
    config = OandaConfig.from_json_file(Path(args.oanda_config)) if getattr(args, "oanda_config", "") else OandaConfig.from_env()
    return run_stream_loop(output_root=output_root, config=config, max_ticks=int(args.max_ticks or 0))


def cmd_demo_us30_monday_or_paper_status(args) -> int:
    from .demo.us30_monday_or_paper import status_daemon
    return status_daemon(_demo_us30_monday_or_paper_output_root(args))


def cmd_demo_us30_monday_or_paper_stop(args) -> int:
    from .demo.us30_monday_or_paper import stop_daemon
    return stop_daemon(_demo_us30_monday_or_paper_output_root(args))


def _demo_us30_monday_or_oanda_output_root(args) -> Path:
    from .demo.us30_monday_or_oanda import default_output_root
    return Path(args.output_root) if getattr(args, "output_root", "") else default_output_root()


def cmd_demo_us30_monday_or_oanda(args) -> int:
    from .demo.us30_monday_or_oanda import run_stream_loop, spawn_daemon
    from .oanda import OandaConfig
    output_root = _demo_us30_monday_or_oanda_output_root(args)
    if args.daemon:
        return spawn_daemon(output_root=output_root, max_ticks=int(args.max_ticks or 0), oanda_config_path=getattr(args, "oanda_config", "") or "")
    config = OandaConfig.from_json_file(Path(args.oanda_config)) if getattr(args, "oanda_config", "") else OandaConfig.from_env()
    return run_stream_loop(output_root=output_root, config=config, max_ticks=int(args.max_ticks or 0))


def cmd_demo_us30_monday_or_oanda_status(args) -> int:
    from .demo.us30_monday_or_oanda import status_daemon
    return status_daemon(_demo_us30_monday_or_oanda_output_root(args))


def cmd_demo_us30_monday_or_oanda_stop(args) -> int:
    from .demo.us30_monday_or_oanda import stop_daemon
    return stop_daemon(_demo_us30_monday_or_oanda_output_root(args))


def _demo_eurusd_monday_or_paper_output_root(args) -> Path:
    from .demo.eurusd_monday_or_paper import default_output_root
    return Path(args.output_root) if getattr(args, "output_root", "") else default_output_root()


def cmd_demo_eurusd_monday_or_paper(args) -> int:
    from .demo.eurusd_monday_or_paper import run_stream_loop, spawn_daemon
    from .oanda import OandaConfig
    output_root = _demo_eurusd_monday_or_paper_output_root(args)
    if args.daemon:
        return spawn_daemon(output_root=output_root, max_ticks=int(args.max_ticks or 0), oanda_config_path=getattr(args, "oanda_config", "") or "")
    config = OandaConfig.from_json_file(Path(args.oanda_config)) if getattr(args, "oanda_config", "") else OandaConfig.from_env()
    return run_stream_loop(output_root=output_root, config=config, max_ticks=int(args.max_ticks or 0))


def cmd_demo_eurusd_monday_or_paper_status(args) -> int:
    from .demo.eurusd_monday_or_paper import status_daemon
    return status_daemon(_demo_eurusd_monday_or_paper_output_root(args))


def cmd_demo_eurusd_monday_or_paper_stop(args) -> int:
    from .demo.eurusd_monday_or_paper import stop_daemon
    return stop_daemon(_demo_eurusd_monday_or_paper_output_root(args))


def _demo_usdjpy_asia_range_paper_output_root(args) -> Path:
    from .demo.usdjpy_asia_range_london_paper import default_output_root

    return Path(args.output_root) if getattr(args, "output_root", "") else default_output_root()


def cmd_demo_usdjpy_asia_range_paper(args) -> int:
    from .demo.usdjpy_asia_range_london_common import oanda_config_from_env
    from .demo.usdjpy_asia_range_london_paper import run_stream_loop, spawn_daemon
    from .oanda import OandaConfig

    output_root = _demo_usdjpy_asia_range_paper_output_root(args)
    if args.daemon:
        return spawn_daemon(
            output_root=output_root,
            max_ticks=int(args.max_ticks or 0),
            oanda_config_path=getattr(args, "oanda_config", "") or "",
        )
    config = OandaConfig.from_json_file(Path(args.oanda_config)) if getattr(args, "oanda_config", "") else oanda_config_from_env()
    return run_stream_loop(output_root=output_root, config=config, max_ticks=int(args.max_ticks or 0))


def cmd_demo_usdjpy_asia_range_paper_status(args) -> int:
    from .demo.usdjpy_asia_range_london_paper import status_daemon

    return status_daemon(_demo_usdjpy_asia_range_paper_output_root(args))


def cmd_demo_usdjpy_asia_range_paper_stop(args) -> int:
    from .demo.usdjpy_asia_range_london_paper import stop_daemon

    return stop_daemon(_demo_usdjpy_asia_range_paper_output_root(args))


def _demo_usdjpy_asia_range_oanda_output_root(args) -> Path:
    from .demo.usdjpy_asia_range_london_oanda import default_output_root

    return Path(args.output_root) if getattr(args, "output_root", "") else default_output_root()


def cmd_demo_usdjpy_asia_range_oanda(args) -> int:
    from .demo.usdjpy_asia_range_london_common import oanda_config_from_env
    from .demo.usdjpy_asia_range_london_oanda import run_stream_loop, spawn_daemon
    from .oanda import OandaConfig

    output_root = _demo_usdjpy_asia_range_oanda_output_root(args)
    if args.daemon:
        return spawn_daemon(
            output_root=output_root,
            max_ticks=int(args.max_ticks or 0),
            oanda_config_path=getattr(args, "oanda_config", "") or "",
        )
    config = OandaConfig.from_json_file(Path(args.oanda_config)) if getattr(args, "oanda_config", "") else oanda_config_from_env()
    return run_stream_loop(output_root=output_root, config=config, max_ticks=int(args.max_ticks or 0))


def cmd_demo_usdjpy_asia_range_oanda_status(args) -> int:
    from .demo.usdjpy_asia_range_london_oanda import status_daemon

    return status_daemon(_demo_usdjpy_asia_range_oanda_output_root(args))


def cmd_demo_usdjpy_asia_range_oanda_stop(args) -> int:
    from .demo.usdjpy_asia_range_london_oanda import stop_daemon

    return stop_daemon(_demo_usdjpy_asia_range_oanda_output_root(args))


def _demo_us30_london_prior_opposed_paper_output_root(args) -> Path:
    from .demo.us30_london_prior_opposed_paper import default_output_root

    return Path(args.output_root) if getattr(args, "output_root", "") else default_output_root()


def cmd_demo_us30_london_prior_opposed_paper(args) -> int:
    from .demo.us30_london_prior_opposed_common import oanda_config_from_env
    from .demo.us30_london_prior_opposed_paper import run_stream_loop, spawn_daemon
    from .oanda import OandaConfig

    output_root = _demo_us30_london_prior_opposed_paper_output_root(args)
    if args.daemon:
        return spawn_daemon(
            output_root=output_root,
            max_ticks=int(args.max_ticks or 0),
            oanda_config_path=getattr(args, "oanda_config", "") or "",
        )
    config = (
        OandaConfig.from_json_file(Path(args.oanda_config))
        if getattr(args, "oanda_config", "")
        else oanda_config_from_env()
    )
    return run_stream_loop(output_root=output_root, config=config, max_ticks=int(args.max_ticks or 0))


def cmd_demo_us30_london_prior_opposed_paper_status(args) -> int:
    from .demo.us30_london_prior_opposed_paper import status_daemon

    return status_daemon(_demo_us30_london_prior_opposed_paper_output_root(args))


def cmd_demo_us30_london_prior_opposed_paper_stop(args) -> int:
    from .demo.us30_london_prior_opposed_paper import stop_daemon

    return stop_daemon(_demo_us30_london_prior_opposed_paper_output_root(args))


def _demo_us30_london_prior_opposed_oanda_output_root(args) -> Path:
    from .demo.us30_london_prior_opposed_oanda import default_output_root

    return Path(args.output_root) if getattr(args, "output_root", "") else default_output_root()


def cmd_demo_us30_london_prior_opposed_oanda(args) -> int:
    from .demo.us30_london_prior_opposed_common import oanda_config_from_env
    from .demo.us30_london_prior_opposed_oanda import run_stream_loop, spawn_daemon
    from .oanda import OandaConfig

    output_root = _demo_us30_london_prior_opposed_oanda_output_root(args)
    if args.daemon:
        return spawn_daemon(
            output_root=output_root,
            max_ticks=int(args.max_ticks or 0),
            oanda_config_path=getattr(args, "oanda_config", "") or "",
        )
    config = (
        OandaConfig.from_json_file(Path(args.oanda_config))
        if getattr(args, "oanda_config", "")
        else oanda_config_from_env()
    )
    return run_stream_loop(output_root=output_root, config=config, max_ticks=int(args.max_ticks or 0))


def cmd_demo_us30_london_prior_opposed_oanda_status(args) -> int:
    from .demo.us30_london_prior_opposed_oanda import status_daemon

    return status_daemon(_demo_us30_london_prior_opposed_oanda_output_root(args))


def cmd_demo_us30_london_prior_opposed_oanda_stop(args) -> int:
    from .demo.us30_london_prior_opposed_oanda import stop_daemon

    return stop_daemon(_demo_us30_london_prior_opposed_oanda_output_root(args))


def _demo_us30_st_pmc_paper_output_root(args) -> Path:
    from .demo.us30_hourly_st_pmc_paper import default_output_root

    return Path(args.output_root) if getattr(args, "output_root", "") else default_output_root()


def cmd_demo_us30_hourly_st_pmc_paper(args) -> int:
    from .demo.us30_hourly_st_pmc_paper import run_stream_loop, spawn_daemon
    from .oanda import OandaConfig

    output_root = _demo_us30_st_pmc_paper_output_root(args)
    if args.daemon:
        return spawn_daemon(
            output_root=output_root,
            max_ticks=int(args.max_ticks or 0),
            oanda_config_path=getattr(args, "oanda_config", "") or "",
        )
    config = OandaConfig.from_json_file(Path(args.oanda_config)) if getattr(args, "oanda_config", "") else OandaConfig.from_env()
    return run_stream_loop(output_root=output_root, config=config, max_ticks=int(args.max_ticks or 0))


def cmd_demo_us30_hourly_st_pmc_paper_status(args) -> int:
    from .demo.us30_hourly_st_pmc_paper import status_daemon

    return status_daemon(_demo_us30_st_pmc_paper_output_root(args))


def cmd_demo_us30_hourly_st_pmc_paper_stop(args) -> int:
    from .demo.us30_hourly_st_pmc_paper import stop_daemon

    return stop_daemon(_demo_us30_st_pmc_paper_output_root(args))


def _demo_us30_st_pmc_oanda_output_root(args) -> Path:
    from .demo.us30_hourly_st_pmc_oanda import default_output_root

    return Path(args.output_root) if getattr(args, "output_root", "") else default_output_root()


def cmd_demo_us30_hourly_st_pmc_oanda(args) -> int:
    from .demo.us30_hourly_st_pmc_oanda import run_stream_loop, spawn_daemon
    from .oanda import OandaConfig

    output_root = _demo_us30_st_pmc_oanda_output_root(args)
    if args.daemon:
        return spawn_daemon(
            output_root=output_root,
            max_ticks=int(args.max_ticks or 0),
            oanda_config_path=getattr(args, "oanda_config", "") or "",
        )
    config = OandaConfig.from_json_file(Path(args.oanda_config)) if getattr(args, "oanda_config", "") else OandaConfig.from_env()
    return run_stream_loop(output_root=output_root, config=config, max_ticks=int(args.max_ticks or 0))


def cmd_demo_us30_hourly_st_pmc_oanda_status(args) -> int:
    from .demo.us30_hourly_st_pmc_oanda import status_daemon

    return status_daemon(_demo_us30_st_pmc_oanda_output_root(args))


def cmd_demo_us30_hourly_st_pmc_oanda_stop(args) -> int:
    from .demo.us30_hourly_st_pmc_oanda import stop_daemon

    return stop_daemon(_demo_us30_st_pmc_oanda_output_root(args))


def _demo_nas100_st_pmc_paper_output_root(args) -> Path:
    from .demo.nas100_hourly_st_pmc_paper import default_output_root

    return Path(args.output_root) if getattr(args, "output_root", "") else default_output_root()


def cmd_demo_nas100_hourly_st_pmc_paper(args) -> int:
    from .demo.nas100_hourly_st_pmc_paper import run_stream_loop, spawn_daemon
    from .oanda import OandaConfig

    output_root = _demo_nas100_st_pmc_paper_output_root(args)
    if args.daemon:
        return spawn_daemon(
            output_root=output_root,
            max_ticks=int(args.max_ticks or 0),
            oanda_config_path=getattr(args, "oanda_config", "") or "",
        )
    config = OandaConfig.from_json_file(Path(args.oanda_config)) if getattr(args, "oanda_config", "") else OandaConfig.from_env()
    return run_stream_loop(output_root=output_root, config=config, max_ticks=int(args.max_ticks or 0))


def cmd_demo_nas100_hourly_st_pmc_paper_status(args) -> int:
    from .demo.nas100_hourly_st_pmc_paper import status_daemon

    return status_daemon(_demo_nas100_st_pmc_paper_output_root(args))


def cmd_demo_nas100_hourly_st_pmc_paper_stop(args) -> int:
    from .demo.nas100_hourly_st_pmc_paper import stop_daemon

    return stop_daemon(_demo_nas100_st_pmc_paper_output_root(args))


def _demo_nas100_st_pmc_oanda_output_root(args) -> Path:
    from .demo.nas100_hourly_st_pmc_oanda import default_output_root

    return Path(args.output_root) if getattr(args, "output_root", "") else default_output_root()


def cmd_demo_nas100_hourly_st_pmc_oanda(args) -> int:
    from .demo.nas100_hourly_st_pmc_oanda import run_stream_loop, spawn_daemon
    from .oanda import OandaConfig

    output_root = _demo_nas100_st_pmc_oanda_output_root(args)
    if args.daemon:
        return spawn_daemon(
            output_root=output_root,
            max_ticks=int(args.max_ticks or 0),
            oanda_config_path=getattr(args, "oanda_config", "") or "",
        )
    config = OandaConfig.from_json_file(Path(args.oanda_config)) if getattr(args, "oanda_config", "") else OandaConfig.from_env()
    return run_stream_loop(output_root=output_root, config=config, max_ticks=int(args.max_ticks or 0))


def cmd_demo_nas100_hourly_st_pmc_oanda_status(args) -> int:
    from .demo.nas100_hourly_st_pmc_oanda import status_daemon

    return status_daemon(_demo_nas100_st_pmc_oanda_output_root(args))


def cmd_demo_nas100_hourly_st_pmc_oanda_stop(args) -> int:
    from .demo.nas100_hourly_st_pmc_oanda import stop_daemon

    return stop_daemon(_demo_nas100_st_pmc_oanda_output_root(args))


def _demo_us30_st_pmc_2r10r_paper_output_root(args) -> Path:
    from .demo.us30_hourly_st_pmc_runners_2r_10r_paper import default_output_root

    return Path(args.output_root) if getattr(args, "output_root", "") else default_output_root()


def cmd_demo_us30_hourly_st_pmc_2r10r_paper(args) -> int:
    from .demo.us30_hourly_st_pmc_runners_2r_10r_paper import run_stream_loop, spawn_daemon
    from .oanda import OandaConfig

    output_root = _demo_us30_st_pmc_2r10r_paper_output_root(args)
    if args.daemon:
        return spawn_daemon(
            output_root=output_root,
            max_ticks=int(args.max_ticks or 0),
            oanda_config_path=getattr(args, "oanda_config", "") or "",
        )
    config = OandaConfig.from_json_file(Path(args.oanda_config)) if getattr(args, "oanda_config", "") else OandaConfig.from_env()
    return run_stream_loop(output_root=output_root, config=config, max_ticks=int(args.max_ticks or 0))


def cmd_demo_us30_hourly_st_pmc_2r10r_paper_status(args) -> int:
    from .demo.us30_hourly_st_pmc_runners_2r_10r_paper import status_daemon

    return status_daemon(_demo_us30_st_pmc_2r10r_paper_output_root(args))


def cmd_demo_us30_hourly_st_pmc_2r10r_paper_stop(args) -> int:
    from .demo.us30_hourly_st_pmc_runners_2r_10r_paper import stop_daemon

    return stop_daemon(_demo_us30_st_pmc_2r10r_paper_output_root(args))


def _demo_us30_st_pmc_2r10r_oanda_output_root(args) -> Path:
    from .demo.us30_hourly_st_pmc_runners_2r_10r_oanda import default_output_root

    return Path(args.output_root) if getattr(args, "output_root", "") else default_output_root()


def cmd_demo_us30_hourly_st_pmc_2r10r_oanda(args) -> int:
    from .demo.us30_hourly_st_pmc_runners_2r_10r_oanda import run_stream_loop, spawn_daemon
    from .oanda import OandaConfig

    output_root = _demo_us30_st_pmc_2r10r_oanda_output_root(args)
    if args.daemon:
        return spawn_daemon(
            output_root=output_root,
            max_ticks=int(args.max_ticks or 0),
            oanda_config_path=getattr(args, "oanda_config", "") or "",
        )
    config = OandaConfig.from_json_file(Path(args.oanda_config)) if getattr(args, "oanda_config", "") else OandaConfig.from_env()
    return run_stream_loop(output_root=output_root, config=config, max_ticks=int(args.max_ticks or 0))


def cmd_demo_us30_hourly_st_pmc_2r10r_oanda_status(args) -> int:
    from .demo.us30_hourly_st_pmc_runners_2r_10r_oanda import status_daemon

    return status_daemon(_demo_us30_st_pmc_2r10r_oanda_output_root(args))


def cmd_demo_us30_hourly_st_pmc_2r10r_oanda_stop(args) -> int:
    from .demo.us30_hourly_st_pmc_runners_2r_10r_oanda import stop_daemon

    return stop_daemon(_demo_us30_st_pmc_2r10r_oanda_output_root(args))


def _demo_nas100_st_pmc_2r10r_paper_output_root(args) -> Path:
    from .demo.nas100_hourly_st_pmc_runners_2r_10r_paper import default_output_root

    return Path(args.output_root) if getattr(args, "output_root", "") else default_output_root()


def cmd_demo_nas100_hourly_st_pmc_2r10r_paper(args) -> int:
    from .demo.nas100_hourly_st_pmc_runners_2r_10r_paper import run_stream_loop, spawn_daemon
    from .oanda import OandaConfig

    output_root = _demo_nas100_st_pmc_2r10r_paper_output_root(args)
    if args.daemon:
        return spawn_daemon(
            output_root=output_root,
            max_ticks=int(args.max_ticks or 0),
            oanda_config_path=getattr(args, "oanda_config", "") or "",
        )
    config = OandaConfig.from_json_file(Path(args.oanda_config)) if getattr(args, "oanda_config", "") else OandaConfig.from_env()
    return run_stream_loop(output_root=output_root, config=config, max_ticks=int(args.max_ticks or 0))


def cmd_demo_nas100_hourly_st_pmc_2r10r_paper_status(args) -> int:
    from .demo.nas100_hourly_st_pmc_runners_2r_10r_paper import status_daemon

    return status_daemon(_demo_nas100_st_pmc_2r10r_paper_output_root(args))


def cmd_demo_nas100_hourly_st_pmc_2r10r_paper_stop(args) -> int:
    from .demo.nas100_hourly_st_pmc_runners_2r_10r_paper import stop_daemon

    return stop_daemon(_demo_nas100_st_pmc_2r10r_paper_output_root(args))


def _demo_nas100_st_pmc_2r10r_oanda_output_root(args) -> Path:
    from .demo.nas100_hourly_st_pmc_runners_2r_10r_oanda import default_output_root

    return Path(args.output_root) if getattr(args, "output_root", "") else default_output_root()


def cmd_demo_nas100_hourly_st_pmc_2r10r_oanda(args) -> int:
    from .demo.nas100_hourly_st_pmc_runners_2r_10r_oanda import run_stream_loop, spawn_daemon
    from .oanda import OandaConfig

    output_root = _demo_nas100_st_pmc_2r10r_oanda_output_root(args)
    if args.daemon:
        return spawn_daemon(
            output_root=output_root,
            max_ticks=int(args.max_ticks or 0),
            oanda_config_path=getattr(args, "oanda_config", "") or "",
        )
    config = OandaConfig.from_json_file(Path(args.oanda_config)) if getattr(args, "oanda_config", "") else OandaConfig.from_env()
    return run_stream_loop(output_root=output_root, config=config, max_ticks=int(args.max_ticks or 0))


def cmd_demo_yearly_orb_paper(args) -> int:
    from .demo.yearly_orb_common import default_output_root, run_loop, spawn_daemon, spec_for

    instruments = [x.strip().upper() for x in str(args.instrument).split(",") if x.strip()]
    if getattr(args, "all", False):
        from .demo.yearly_orb_common import SPECS

        instruments = list(SPECS.keys())
    if not instruments:
        print("Need --instrument or --all")
        return 2
    code = 0
    for inst in instruments:
        spec = spec_for(inst)
        output_root = Path(args.output_root) if args.output_root else default_output_root(spec, oanda=False)
        if args.daemon:
            rc = spawn_daemon(
                inst,
                oanda_routing=False,
                output_root=output_root,
                max_polls=int(args.max_polls or 0),
                cli_command="demo-yearly-orb-paper",
            )
        else:
            rc = run_loop(
                inst,
                oanda_routing=False,
                output_root=output_root,
                max_polls=int(args.max_polls or 0),
            )
        code = code or rc
    return code


def cmd_demo_yearly_orb_paper_status(args) -> int:
    from .demo.yearly_orb_common import SPECS, default_output_root, status_daemon

    if args.output_root:
        return status_daemon(Path(args.output_root))
    code = 0
    for spec in SPECS.values():
        code = status_daemon(default_output_root(spec, oanda=False)) or code
    return code


def cmd_demo_yearly_orb_paper_stop(args) -> int:
    from .demo.yearly_orb_common import SPECS, default_output_root, stop_daemon

    if args.output_root:
        return stop_daemon(Path(args.output_root))
    code = 0
    for spec in SPECS.values():
        code = stop_daemon(default_output_root(spec, oanda=False)) or code
    return code


def cmd_demo_yearly_orb_oanda(args) -> int:
    from .demo.yearly_orb_common import default_output_root, run_loop, spawn_daemon, spec_for

    instruments = [x.strip().upper() for x in str(args.instrument).split(",") if x.strip()]
    if getattr(args, "all", False):
        from .demo.yearly_orb_common import SPECS

        instruments = list(SPECS.keys())
    if not instruments:
        print("Need --instrument or --all")
        return 2
    code = 0
    for inst in instruments:
        spec = spec_for(inst)
        output_root = Path(args.output_root) if args.output_root else default_output_root(spec, oanda=True)
        if args.daemon:
            rc = spawn_daemon(
                inst,
                oanda_routing=True,
                output_root=output_root,
                max_polls=int(args.max_polls or 0),
                cli_command="demo-yearly-orb-oanda",
            )
        else:
            rc = run_loop(
                inst,
                oanda_routing=True,
                output_root=output_root,
                max_polls=int(args.max_polls or 0),
            )
        code = code or rc
    return code


def cmd_demo_yearly_orb_oanda_status(args) -> int:
    from .demo.yearly_orb_common import SPECS, default_output_root, status_daemon

    if args.output_root:
        return status_daemon(Path(args.output_root))
    code = 0
    for spec in SPECS.values():
        code = status_daemon(default_output_root(spec, oanda=True)) or code
    return code


def cmd_demo_yearly_orb_oanda_stop(args) -> int:
    from .demo.yearly_orb_common import SPECS, default_output_root, stop_daemon

    if args.output_root:
        return stop_daemon(Path(args.output_root))
    code = 0
    for spec in SPECS.values():
        code = stop_daemon(default_output_root(spec, oanda=True)) or code
    return code


def cmd_demo_nas100_hourly_st_pmc_2r10r_oanda_status(args) -> int:
    from .demo.nas100_hourly_st_pmc_runners_2r_10r_oanda import status_daemon

    return status_daemon(_demo_nas100_st_pmc_2r10r_oanda_output_root(args))


def cmd_demo_nas100_hourly_st_pmc_2r10r_oanda_stop(args) -> int:
    from .demo.nas100_hourly_st_pmc_runners_2r_10r_oanda import stop_daemon

    return stop_daemon(_demo_nas100_st_pmc_2r10r_oanda_output_root(args))


def cmd_oanda_practice_order_smoke(args) -> int:
    """Place a tiny practice EURUSD market order, reconcile via Account Changes, then flatten."""
    from .demo.practice_order_smoke import run_practice_order_smoke

    return run_practice_order_smoke(
        oanda_config_path=getattr(args, "oanda_config", "") or "",
        units=int(getattr(args, "units", 1) or 1),
        state_root=Path(args.state_root),
    )


def cmd_oanda_practice_sync(args) -> int:
    """Query OANDA practice account; optionally repair local *_oanda demo positions.csv."""
    from .demo.oanda_practice_sync import main as oanda_practice_sync_main

    argv = []
    if getattr(args, "repair_demo_positions", False):
        argv.append("--repair-demo-positions")
    return oanda_practice_sync_main(argv)


def cmd_cqg_smoke(args) -> int:
    from .cqg import CqgMarketDataFeedAdapter, CqgWebApiClient, JsonCqgProtocolCodec

    store = _store(args)
    store.ensure()
    config = _cqg_config(args)
    client = CqgWebApiClient(config=config, store=store, codec=JsonCqgProtocolCodec())
    store.append_event(
        "cqg_session_events",
        {
            "event": "smoke_start",
            "offline": bool(args.offline),
            "env": config.env,
            "endpoint": config.endpoint,
            "instrument": args.instrument,
        },
    )
    if args.offline:
        adapter = CqgMarketDataFeedAdapter(store, config=config)
        if args.contract_id:
            adapter.resolve_contract(args.instrument, args.contract_id, cqg_symbol=config.contract_map.get(args.instrument.upper(), ""))
        print(
            "CQG offline smoke ok: env=%s endpoint=%s instrument=%s account=%s"
            % (config.env, config.endpoint, args.instrument, config.account_id or "<unset>")
        )
        return 0

    config.validate_for_network()
    logon = client.build_logon_message()
    symbol = client.build_symbol_resolution_request(args.instrument)
    account = client.build_account_request()
    trade_sub = client.build_trade_subscription()
    # The real transport is enabled after CQG protobuf generation is installed.
    encoded = [client.encode(item) for item in (logon, symbol, account, trade_sub)]
    store.append_event(
        "cqg_session_events",
        {
            "event": "smoke_messages_built",
            "message_count": len(encoded),
            "instrument": args.instrument,
            "note": "network transport requires CQG generated protobuf files and demo credentials",
        },
    )
    print("CQG smoke messages built; install protobuf transport before live demo connect")
    return 0


def cmd_cqg_feed_shadow(args) -> int:
    from .cqg import CqgMarketDataFeedAdapter, load_jsonl_events

    if not args.events:
        raise SystemExit("cqg-feed-shadow currently requires --events JSONL for offline replay")
    store = _store(args)
    adapter = CqgMarketDataFeedAdapter(store, config=_cqg_config(args))
    count = 0
    emitted = 0
    for event in load_jsonl_events(Path(args.events)):
        count += 1
        emitted += len(adapter.on_raw_event(event))
    emitted += len(adapter.flush())
    health = adapter.health()
    print(
        "CQG feed shadow replayed %d events, emitted %d bars, status=%s reason=%s"
        % (count, emitted, health.status, adapter.blocking_reason() or "none")
    )
    return 0


def cmd_cqg_paper(args) -> int:
    from .cqg import CqgBroker, CqgMarketDataFeedAdapter, load_jsonl_events

    store = _store(args)
    config = _cqg_config(args)
    broker = CqgBroker(store, config=config, allow_live_routing=False)
    adapter = CqgMarketDataFeedAdapter(store, config=config)
    count = 0
    emitted = 0
    if args.events:
        for event in load_jsonl_events(Path(args.events)):
            count += 1
            event_type = str(event.get("type") or "")
            if event_type == "order_status":
                broker.on_order_status(event)
            elif event_type == "fill":
                broker.on_fill(event)
            else:
                emitted += len(adapter.on_raw_event(event))
        emitted += len(adapter.flush())
    store.append_event(
        "cqg_session_events",
        {
            "event": "cqg_paper_ready",
            "events_replayed": count,
            "bars_emitted": emitted,
            "active_orders": len(broker.reconcile_orders()),
            "positions": len(broker.reconcile_positions()),
            "note": "CQG demo/sim routing requires credentials and generated protobuf transport",
        },
    )
    print(
        "CQG paper scaffold ready: replayed %d events, emitted %d bars, active_orders=%d"
        % (count, emitted, len(broker.reconcile_orders()))
    )
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

    tradovate_smoke = sub.add_parser("tradovate-smoke", help="Validate Tradovate OpenAPI/config/session scaffolding")
    tradovate_smoke.add_argument("--tradovate-config", default="")
    tradovate_smoke.add_argument("--instruments", default="MNQ,NQ,MYM")
    tradovate_smoke.add_argument("--contract-id", default="")
    tradovate_smoke.add_argument("--offline", action="store_true")
    tradovate_smoke.set_defaults(func=cmd_tradovate_smoke)

    tradovate_feed = sub.add_parser("tradovate-feed-shadow", help="Replay Tradovate JSONL events into live feed state")
    tradovate_feed.add_argument("--tradovate-config", default="")
    tradovate_feed.add_argument("--events", default="")
    tradovate_feed.set_defaults(func=cmd_tradovate_feed_shadow)

    tradovate_paper = sub.add_parser("tradovate-paper", help="Bootstrap Tradovate demo/sim broker/feed state")
    tradovate_paper.add_argument("--tradovate-config", default="")
    tradovate_paper.add_argument("--events", default="")
    tradovate_paper.add_argument("--server-oco-validated", action="store_true")
    tradovate_paper.set_defaults(func=cmd_tradovate_paper)

    tradovate_flat = sub.add_parser("tradovate-emergency-flatten", help="Cancel/flatten Tradovate MNQ/NQ/MYM state")
    tradovate_flat.add_argument("--tradovate-config", default="")
    tradovate_flat.add_argument("--instruments", default="MNQ,NQ,MYM")
    tradovate_flat.add_argument("--allow-live", action="store_true")
    tradovate_flat.set_defaults(func=cmd_tradovate_emergency_flatten)

    oanda_smoke = sub.add_parser("oanda-smoke", help="Validate OANDA config/account/pricing scaffolding")
    oanda_smoke.add_argument("--oanda-config", default="")
    oanda_smoke.add_argument("--instruments", default="EURUSD,XAUUSD")
    oanda_smoke.add_argument("--offline", action="store_true")
    oanda_smoke.set_defaults(func=cmd_oanda_smoke)

    oanda_stream = sub.add_parser("oanda-stream-prices", help="Stream OANDA bid/ask prices to the console")
    oanda_stream.add_argument("--oanda-config", default="")
    oanda_stream.add_argument("--instruments", default="EURUSD,XAUUSD")
    oanda_stream.add_argument("--max-ticks", type=int, default=0, help="Stop after N price ticks (0 = run forever)")
    oanda_stream.add_argument("--heartbeats", action="store_true", help="Also print HEARTBEAT lines")
    oanda_stream.add_argument("--no-snapshot", action="store_true", help="Skip initial pricing snapshot")
    oanda_stream.set_defaults(func=cmd_oanda_stream_prices)

    oanda_feed = sub.add_parser("oanda-feed-shadow", help="Replay OANDA-like JSONL events into live feed state")
    oanda_feed.add_argument("--oanda-config", default="")
    oanda_feed.add_argument("--events", default="")
    oanda_feed.set_defaults(func=cmd_oanda_feed_shadow)

    oanda_paper = sub.add_parser("oanda-paper", help="Bootstrap OANDA practice broker/feed state")
    oanda_paper.add_argument("--oanda-config", default="")
    oanda_paper.add_argument("--events", default="")
    oanda_paper.set_defaults(func=cmd_oanda_paper)

    oanda_flat = sub.add_parser("oanda-emergency-flatten", help="Cancel/flatten OANDA EURUSD/XAUUSD state")
    oanda_flat.add_argument("--oanda-config", default="")
    oanda_flat.add_argument("--instruments", default="EURUSD,XAUUSD")
    oanda_flat.add_argument("--allow-live", action="store_true")
    oanda_flat.set_defaults(func=cmd_oanda_emergency_flatten)

    demo_paper = sub.add_parser(
        "demo-eurusd-v2b-paper",
        help="EURUSD v2b ungated paper demo (OANDA prices, local PaperBroker; --daemon for background)",
    )
    demo_paper.add_argument("--output-root", default="", help="Default: live/demo/eurusd_v2b_ungated_paper")
    demo_paper.add_argument("--oanda-config", default="")
    demo_paper.add_argument("--daemon", action="store_true", help="Detach to background (run.log + pidfile)")
    demo_paper.add_argument("--max-ticks", type=int, default=0, help="Stop after N price ticks (0 = forever)")
    demo_paper.set_defaults(func=cmd_demo_eurusd_v2b_paper)

    demo_status = sub.add_parser("demo-eurusd-v2b-paper-status", help="Status of EURUSD demo paper daemon")
    demo_status.add_argument("--output-root", default="")
    demo_status.set_defaults(func=cmd_demo_eurusd_v2b_paper_status)

    demo_stop = sub.add_parser("demo-eurusd-v2b-paper-stop", help="Stop EURUSD demo paper daemon")
    demo_stop.add_argument("--output-root", default="")
    demo_stop.set_defaults(func=cmd_demo_eurusd_v2b_paper_stop)

    demo_nas = sub.add_parser(
        "demo-nas100-v2b-paper",
        help="NAS100 v2b ungated paper demo (OANDA NAS100_USD prices, local PaperBroker; --daemon)",
    )
    demo_nas.add_argument("--output-root", default="", help="Default: live/demo/nas100_v2b_ungated_paper")
    demo_nas.add_argument("--oanda-config", default="")
    demo_nas.add_argument("--daemon", action="store_true", help="Detach to background (run.log + pidfile)")
    demo_nas.add_argument("--max-ticks", type=int, default=0, help="Stop after N price ticks (0 = forever)")
    demo_nas.set_defaults(func=cmd_demo_nas100_v2b_paper)

    demo_nas_status = sub.add_parser("demo-nas100-v2b-paper-status", help="Status of NAS100 demo paper daemon")
    demo_nas_status.add_argument("--output-root", default="")
    demo_nas_status.set_defaults(func=cmd_demo_nas100_v2b_paper_status)

    demo_nas_stop = sub.add_parser("demo-nas100-v2b-paper-stop", help="Stop NAS100 demo paper daemon")
    demo_nas_stop.add_argument("--output-root", default="")
    demo_nas_stop.set_defaults(func=cmd_demo_nas100_v2b_paper_stop)

    demo_spx = sub.add_parser(
        "demo-spx500-v2b-paper",
        help="SPX500 v2b ungated paper demo (OANDA SPX500_USD / ES proxy; --daemon)",
    )
    demo_spx.add_argument("--output-root", default="", help="Default: live/demo/spx500_v2b_ungated_paper")
    demo_spx.add_argument("--oanda-config", default="")
    demo_spx.add_argument("--daemon", action="store_true")
    demo_spx.add_argument("--max-ticks", type=int, default=0)
    demo_spx.set_defaults(func=cmd_demo_spx500_v2b_paper)

    demo_spx_status = sub.add_parser("demo-spx500-v2b-paper-status", help="Status of SPX500 demo paper daemon")
    demo_spx_status.add_argument("--output-root", default="")
    demo_spx_status.set_defaults(func=cmd_demo_spx500_v2b_paper_status)

    demo_spx_stop = sub.add_parser("demo-spx500-v2b-paper-stop", help="Stop SPX500 demo paper daemon")
    demo_spx_stop.add_argument("--output-root", default="")
    demo_spx_stop.set_defaults(func=cmd_demo_spx500_v2b_paper_stop)

    demo_us30 = sub.add_parser(
        "demo-us30-v2b-paper",
        help="US30 v2b ungated paper demo (OANDA US30_USD / YM proxy; --daemon)",
    )
    demo_us30.add_argument("--output-root", default="", help="Default: live/demo/us30_v2b_ungated_paper")
    demo_us30.add_argument("--oanda-config", default="")
    demo_us30.add_argument("--daemon", action="store_true")
    demo_us30.add_argument("--max-ticks", type=int, default=0)
    demo_us30.set_defaults(func=cmd_demo_us30_v2b_paper)

    demo_us30_status = sub.add_parser("demo-us30-v2b-paper-status", help="Status of US30 demo paper daemon")
    demo_us30_status.add_argument("--output-root", default="")
    demo_us30_status.set_defaults(func=cmd_demo_us30_v2b_paper_status)

    demo_us30_stop = sub.add_parser("demo-us30-v2b-paper-stop", help="Stop US30 demo paper daemon")
    demo_us30_stop.add_argument("--output-root", default="")
    demo_us30_stop.set_defaults(func=cmd_demo_us30_v2b_paper_stop)

    demo_eurusd_oanda = sub.add_parser(
        "demo-eurusd-v2b-oanda",
        help="EURUSD v2b ungated OANDA practice demo (real practice orders; --daemon)",
    )
    demo_eurusd_oanda.add_argument("--output-root", default="", help="Default: live/demo/eurusd_v2b_ungated_oanda")
    demo_eurusd_oanda.add_argument("--oanda-config", default="")
    demo_eurusd_oanda.add_argument("--daemon", action="store_true")
    demo_eurusd_oanda.add_argument("--max-ticks", type=int, default=0)
    demo_eurusd_oanda.set_defaults(func=cmd_demo_eurusd_v2b_oanda)

    demo_eurusd_oanda_status = sub.add_parser("demo-eurusd-v2b-oanda-status", help="Status of EURUSD OANDA practice demo")
    demo_eurusd_oanda_status.add_argument("--output-root", default="")
    demo_eurusd_oanda_status.set_defaults(func=cmd_demo_eurusd_v2b_oanda_status)

    demo_eurusd_oanda_stop = sub.add_parser("demo-eurusd-v2b-oanda-stop", help="Stop EURUSD OANDA practice demo")
    demo_eurusd_oanda_stop.add_argument("--output-root", default="")
    demo_eurusd_oanda_stop.set_defaults(func=cmd_demo_eurusd_v2b_oanda_stop)

    demo_nas_oanda = sub.add_parser(
        "demo-nas100-v2b-oanda",
        help="NAS100 v2b ungated OANDA practice demo (real practice orders; --daemon)",
    )
    demo_nas_oanda.add_argument("--output-root", default="", help="Default: live/demo/nas100_v2b_ungated_oanda")
    demo_nas_oanda.add_argument("--oanda-config", default="")
    demo_nas_oanda.add_argument("--daemon", action="store_true")
    demo_nas_oanda.add_argument("--max-ticks", type=int, default=0)
    demo_nas_oanda.set_defaults(func=cmd_demo_nas100_v2b_oanda)

    demo_nas_oanda_status = sub.add_parser("demo-nas100-v2b-oanda-status", help="Status of NAS100 OANDA practice demo")
    demo_nas_oanda_status.add_argument("--output-root", default="")
    demo_nas_oanda_status.set_defaults(func=cmd_demo_nas100_v2b_oanda_status)

    demo_nas_oanda_stop = sub.add_parser("demo-nas100-v2b-oanda-stop", help="Stop NAS100 OANDA practice demo")
    demo_nas_oanda_stop.add_argument("--output-root", default="")
    demo_nas_oanda_stop.set_defaults(func=cmd_demo_nas100_v2b_oanda_stop)

    demo_spx_oanda = sub.add_parser(
        "demo-spx500-v2b-oanda",
        help="SPX500 v2b ungated OANDA practice demo (real practice orders; --daemon)",
    )
    demo_spx_oanda.add_argument("--output-root", default="", help="Default: live/demo/spx500_v2b_ungated_oanda")
    demo_spx_oanda.add_argument("--oanda-config", default="")
    demo_spx_oanda.add_argument("--daemon", action="store_true")
    demo_spx_oanda.add_argument("--max-ticks", type=int, default=0)
    demo_spx_oanda.set_defaults(func=cmd_demo_spx500_v2b_oanda)

    demo_spx_oanda_status = sub.add_parser("demo-spx500-v2b-oanda-status", help="Status of SPX500 OANDA practice demo")
    demo_spx_oanda_status.add_argument("--output-root", default="")
    demo_spx_oanda_status.set_defaults(func=cmd_demo_spx500_v2b_oanda_status)

    demo_spx_oanda_stop = sub.add_parser("demo-spx500-v2b-oanda-stop", help="Stop SPX500 OANDA practice demo")
    demo_spx_oanda_stop.add_argument("--output-root", default="")
    demo_spx_oanda_stop.set_defaults(func=cmd_demo_spx500_v2b_oanda_stop)

    demo_us30_oanda = sub.add_parser(
        "demo-us30-v2b-oanda",
        help="US30 v2b ungated OANDA practice demo (real practice orders; --daemon)",
    )
    demo_us30_oanda.add_argument("--output-root", default="", help="Default: live/demo/us30_v2b_ungated_oanda")
    demo_us30_oanda.add_argument("--oanda-config", default="")
    demo_us30_oanda.add_argument("--daemon", action="store_true")
    demo_us30_oanda.add_argument("--max-ticks", type=int, default=0)
    demo_us30_oanda.set_defaults(func=cmd_demo_us30_v2b_oanda)

    demo_us30_oanda_status = sub.add_parser("demo-us30-v2b-oanda-status", help="Status of US30 OANDA practice demo")
    demo_us30_oanda_status.add_argument("--output-root", default="")
    demo_us30_oanda_status.set_defaults(func=cmd_demo_us30_v2b_oanda_status)

    demo_us30_oanda_stop = sub.add_parser("demo-us30-v2b-oanda-stop", help="Stop US30 OANDA practice demo")
    demo_us30_oanda_stop.add_argument("--output-root", default="")
    demo_us30_oanda_stop.set_defaults(func=cmd_demo_us30_v2b_oanda_stop)

    demo_usdjpy_mo = sub.add_parser(
        "demo-usdjpy-monday-or-oanda",
        help="USDJPY Monday OR M2_S3_R1 OANDA practice demo (15m; real practice orders; --daemon)",
    )
    demo_usdjpy_mo.add_argument("--output-root", default="", help="Default: live/demo/usdjpy_monday_or_ungated_oanda")
    demo_usdjpy_mo.add_argument("--oanda-config", default="")
    demo_usdjpy_mo.add_argument("--daemon", action="store_true")
    demo_usdjpy_mo.add_argument("--max-ticks", type=int, default=0)
    demo_usdjpy_mo.set_defaults(func=cmd_demo_usdjpy_monday_or_oanda)

    demo_usdjpy_mo_status = sub.add_parser(
        "demo-usdjpy-monday-or-oanda-status",
        help="Status of USDJPY Monday OR OANDA practice demo",
    )
    demo_usdjpy_mo_status.add_argument("--output-root", default="")
    demo_usdjpy_mo_status.set_defaults(func=cmd_demo_usdjpy_monday_or_oanda_status)

    demo_usdjpy_mo_stop = sub.add_parser(
        "demo-usdjpy-monday-or-oanda-stop",
        help="Stop USDJPY Monday OR OANDA practice demo",
    )
    demo_usdjpy_mo_stop.add_argument("--output-root", default="")
    demo_usdjpy_mo_stop.set_defaults(func=cmd_demo_usdjpy_monday_or_oanda_stop)

    demo_usdjpy_mo_paper = sub.add_parser(
        "demo-usdjpy-monday-or-paper",
        help="USDJPY Monday OR M2_S3_R1 paper demo (15m; PaperBroker; Fri 15:59 ET flatten; --daemon)",
    )
    demo_usdjpy_mo_paper.add_argument("--output-root", default="", help="Default: live/demo/usdjpy_monday_or_ungated_paper")
    demo_usdjpy_mo_paper.add_argument("--oanda-config", default="")
    demo_usdjpy_mo_paper.add_argument("--daemon", action="store_true")
    demo_usdjpy_mo_paper.add_argument("--max-ticks", type=int, default=0)
    demo_usdjpy_mo_paper.set_defaults(func=cmd_demo_usdjpy_monday_or_paper)

    demo_usdjpy_mo_paper_status = sub.add_parser(
        "demo-usdjpy-monday-or-paper-status",
        help="Status of USDJPY Monday OR paper demo",
    )
    demo_usdjpy_mo_paper_status.add_argument("--output-root", default="")
    demo_usdjpy_mo_paper_status.set_defaults(func=cmd_demo_usdjpy_monday_or_paper_status)

    demo_usdjpy_mo_paper_stop = sub.add_parser(
        "demo-usdjpy-monday-or-paper-stop",
        help="Stop USDJPY Monday OR paper demo",
    )
    demo_usdjpy_mo_paper_stop.add_argument("--output-root", default="")
    demo_usdjpy_mo_paper_stop.set_defaults(func=cmd_demo_usdjpy_monday_or_paper_stop)

    demo_usdjpy_asia_paper = sub.add_parser(
        "demo-usdjpy-asia-range-paper",
        help="USDJPY Asia-range London S_3_1_3 filtered paper demo (Jan skip + shadow roll50)",
    )
    demo_usdjpy_asia_paper.add_argument("--output-root", default="")
    demo_usdjpy_asia_paper.add_argument("--oanda-config", default="")
    demo_usdjpy_asia_paper.add_argument("--max-ticks", type=int, default=0)
    demo_usdjpy_asia_paper.add_argument("--daemon", action="store_true")
    demo_usdjpy_asia_paper.set_defaults(func=cmd_demo_usdjpy_asia_range_paper)

    demo_usdjpy_asia_paper_status = sub.add_parser(
        "demo-usdjpy-asia-range-paper-status",
        help="Status of USDJPY Asia-range filtered paper demo",
    )
    demo_usdjpy_asia_paper_status.add_argument("--output-root", default="")
    demo_usdjpy_asia_paper_status.set_defaults(func=cmd_demo_usdjpy_asia_range_paper_status)

    demo_usdjpy_asia_paper_stop = sub.add_parser(
        "demo-usdjpy-asia-range-paper-stop",
        help="Stop USDJPY Asia-range filtered paper demo",
    )
    demo_usdjpy_asia_paper_stop.add_argument("--output-root", default="")
    demo_usdjpy_asia_paper_stop.set_defaults(func=cmd_demo_usdjpy_asia_range_paper_stop)

    demo_usdjpy_asia_oanda = sub.add_parser(
        "demo-usdjpy-asia-range-oanda",
        help="USDJPY Asia-range London S_3_1_3 filtered OANDA practice demo",
    )
    demo_usdjpy_asia_oanda.add_argument("--output-root", default="")
    demo_usdjpy_asia_oanda.add_argument("--oanda-config", default="")
    demo_usdjpy_asia_oanda.add_argument("--max-ticks", type=int, default=0)
    demo_usdjpy_asia_oanda.add_argument("--daemon", action="store_true")
    demo_usdjpy_asia_oanda.set_defaults(func=cmd_demo_usdjpy_asia_range_oanda)

    demo_usdjpy_asia_oanda_status = sub.add_parser(
        "demo-usdjpy-asia-range-oanda-status",
        help="Status of USDJPY Asia-range filtered OANDA demo",
    )
    demo_usdjpy_asia_oanda_status.add_argument("--output-root", default="")
    demo_usdjpy_asia_oanda_status.set_defaults(func=cmd_demo_usdjpy_asia_range_oanda_status)

    demo_usdjpy_asia_oanda_stop = sub.add_parser(
        "demo-usdjpy-asia-range-oanda-stop",
        help="Stop USDJPY Asia-range filtered OANDA demo",
    )
    demo_usdjpy_asia_oanda_stop.add_argument("--output-root", default="")
    demo_usdjpy_asia_oanda_stop.set_defaults(func=cmd_demo_usdjpy_asia_range_oanda_stop)

    demo_us30_london_po_paper = sub.add_parser(
        "demo-us30-london-prior-opposed-paper",
        help="US30 London prior-opposed delayed-arming paper demo (0.25 size, live ST gate)",
    )
    demo_us30_london_po_paper.add_argument("--output-root", default="")
    demo_us30_london_po_paper.add_argument("--oanda-config", default="")
    demo_us30_london_po_paper.add_argument("--max-ticks", type=int, default=0)
    demo_us30_london_po_paper.add_argument("--daemon", action="store_true")
    demo_us30_london_po_paper.set_defaults(func=cmd_demo_us30_london_prior_opposed_paper)

    demo_us30_london_po_paper_status = sub.add_parser(
        "demo-us30-london-prior-opposed-paper-status",
        help="Status of US30 London prior-opposed paper demo",
    )
    demo_us30_london_po_paper_status.add_argument("--output-root", default="")
    demo_us30_london_po_paper_status.set_defaults(func=cmd_demo_us30_london_prior_opposed_paper_status)

    demo_us30_london_po_paper_stop = sub.add_parser(
        "demo-us30-london-prior-opposed-paper-stop",
        help="Stop US30 London prior-opposed paper demo",
    )
    demo_us30_london_po_paper_stop.add_argument("--output-root", default="")
    demo_us30_london_po_paper_stop.set_defaults(func=cmd_demo_us30_london_prior_opposed_paper_stop)

    demo_us30_london_po_oanda = sub.add_parser(
        "demo-us30-london-prior-opposed-oanda",
        help="US30 London prior-opposed delayed-arming OANDA practice demo (0.25 size, live ST gate)",
    )
    demo_us30_london_po_oanda.add_argument("--output-root", default="")
    demo_us30_london_po_oanda.add_argument("--oanda-config", default="")
    demo_us30_london_po_oanda.add_argument("--max-ticks", type=int, default=0)
    demo_us30_london_po_oanda.add_argument("--daemon", action="store_true")
    demo_us30_london_po_oanda.set_defaults(func=cmd_demo_us30_london_prior_opposed_oanda)

    demo_us30_london_po_oanda_status = sub.add_parser(
        "demo-us30-london-prior-opposed-oanda-status",
        help="Status of US30 London prior-opposed OANDA demo",
    )
    demo_us30_london_po_oanda_status.add_argument("--output-root", default="")
    demo_us30_london_po_oanda_status.set_defaults(func=cmd_demo_us30_london_prior_opposed_oanda_status)

    demo_us30_london_po_oanda_stop = sub.add_parser(
        "demo-us30-london-prior-opposed-oanda-stop",
        help="Stop US30 London prior-opposed OANDA demo",
    )
    demo_us30_london_po_oanda_stop.add_argument("--output-root", default="")
    demo_us30_london_po_oanda_stop.set_defaults(func=cmd_demo_us30_london_prior_opposed_oanda_stop)

    demo_us30_st_pmc_paper = sub.add_parser(
        "demo-us30-hourly-st-pmc-paper",
        help="US30 hourly ST+PMC sl50_tp150_3r paper demo (OANDA prices, PaperBroker)",
    )
    demo_us30_st_pmc_paper.add_argument("--output-root", default="")
    demo_us30_st_pmc_paper.add_argument("--oanda-config", default="")
    demo_us30_st_pmc_paper.add_argument("--max-ticks", type=int, default=0)
    demo_us30_st_pmc_paper.add_argument("--daemon", action="store_true")
    demo_us30_st_pmc_paper.set_defaults(func=cmd_demo_us30_hourly_st_pmc_paper)

    demo_us30_st_pmc_paper_status = sub.add_parser(
        "demo-us30-hourly-st-pmc-paper-status",
        help="Status of US30 hourly ST+PMC paper demo",
    )
    demo_us30_st_pmc_paper_status.add_argument("--output-root", default="")
    demo_us30_st_pmc_paper_status.set_defaults(func=cmd_demo_us30_hourly_st_pmc_paper_status)

    demo_us30_st_pmc_paper_stop = sub.add_parser(
        "demo-us30-hourly-st-pmc-paper-stop",
        help="Stop US30 hourly ST+PMC paper demo",
    )
    demo_us30_st_pmc_paper_stop.add_argument("--output-root", default="")
    demo_us30_st_pmc_paper_stop.set_defaults(func=cmd_demo_us30_hourly_st_pmc_paper_stop)

    demo_us30_st_pmc_oanda = sub.add_parser(
        "demo-us30-hourly-st-pmc-oanda",
        help="US30 hourly ST+PMC sl50_tp150_3r OANDA practice demo",
    )
    demo_us30_st_pmc_oanda.add_argument("--output-root", default="")
    demo_us30_st_pmc_oanda.add_argument("--oanda-config", default="")
    demo_us30_st_pmc_oanda.add_argument("--max-ticks", type=int, default=0)
    demo_us30_st_pmc_oanda.add_argument("--daemon", action="store_true")
    demo_us30_st_pmc_oanda.set_defaults(func=cmd_demo_us30_hourly_st_pmc_oanda)

    demo_us30_st_pmc_oanda_status = sub.add_parser(
        "demo-us30-hourly-st-pmc-oanda-status",
        help="Status of US30 hourly ST+PMC OANDA practice demo",
    )
    demo_us30_st_pmc_oanda_status.add_argument("--output-root", default="")
    demo_us30_st_pmc_oanda_status.set_defaults(func=cmd_demo_us30_hourly_st_pmc_oanda_status)

    demo_us30_st_pmc_oanda_stop = sub.add_parser(
        "demo-us30-hourly-st-pmc-oanda-stop",
        help="Stop US30 hourly ST+PMC OANDA practice demo",
    )
    demo_us30_st_pmc_oanda_stop.add_argument("--output-root", default="")
    demo_us30_st_pmc_oanda_stop.set_defaults(func=cmd_demo_us30_hourly_st_pmc_oanda_stop)

    demo_nas100_st_pmc_paper = sub.add_parser(
        "demo-nas100-hourly-st-pmc-paper",
        help="NAS100 hourly ST+PMC sl50_tp150_3r 1mfill paper demo (OANDA prices, PaperBroker)",
    )
    demo_nas100_st_pmc_paper.add_argument("--output-root", default="")
    demo_nas100_st_pmc_paper.add_argument("--oanda-config", default="")
    demo_nas100_st_pmc_paper.add_argument("--max-ticks", type=int, default=0)
    demo_nas100_st_pmc_paper.add_argument("--daemon", action="store_true")
    demo_nas100_st_pmc_paper.set_defaults(func=cmd_demo_nas100_hourly_st_pmc_paper)

    demo_nas100_st_pmc_paper_status = sub.add_parser(
        "demo-nas100-hourly-st-pmc-paper-status",
        help="Status of NAS100 hourly ST+PMC paper demo",
    )
    demo_nas100_st_pmc_paper_status.add_argument("--output-root", default="")
    demo_nas100_st_pmc_paper_status.set_defaults(func=cmd_demo_nas100_hourly_st_pmc_paper_status)

    demo_nas100_st_pmc_paper_stop = sub.add_parser(
        "demo-nas100-hourly-st-pmc-paper-stop",
        help="Stop NAS100 hourly ST+PMC paper demo",
    )
    demo_nas100_st_pmc_paper_stop.add_argument("--output-root", default="")
    demo_nas100_st_pmc_paper_stop.set_defaults(func=cmd_demo_nas100_hourly_st_pmc_paper_stop)

    demo_nas100_st_pmc_oanda = sub.add_parser(
        "demo-nas100-hourly-st-pmc-oanda",
        help="NAS100 hourly ST+PMC sl50_tp150_3r 1mfill OANDA practice demo",
    )
    demo_nas100_st_pmc_oanda.add_argument("--output-root", default="")
    demo_nas100_st_pmc_oanda.add_argument("--oanda-config", default="")
    demo_nas100_st_pmc_oanda.add_argument("--max-ticks", type=int, default=0)
    demo_nas100_st_pmc_oanda.add_argument("--daemon", action="store_true")
    demo_nas100_st_pmc_oanda.set_defaults(func=cmd_demo_nas100_hourly_st_pmc_oanda)

    demo_nas100_st_pmc_oanda_status = sub.add_parser(
        "demo-nas100-hourly-st-pmc-oanda-status",
        help="Status of NAS100 hourly ST+PMC OANDA practice demo",
    )
    demo_nas100_st_pmc_oanda_status.add_argument("--output-root", default="")
    demo_nas100_st_pmc_oanda_status.set_defaults(func=cmd_demo_nas100_hourly_st_pmc_oanda_status)

    demo_nas100_st_pmc_oanda_stop = sub.add_parser(
        "demo-nas100-hourly-st-pmc-oanda-stop",
        help="Stop NAS100 hourly ST+PMC OANDA practice demo",
    )
    demo_nas100_st_pmc_oanda_stop.add_argument("--output-root", default="")
    demo_nas100_st_pmc_oanda_stop.set_defaults(func=cmd_demo_nas100_hourly_st_pmc_oanda_stop)

    demo_us30_st_pmc_2r10r_paper = sub.add_parser(
        "demo-us30-hourly-st-pmc-2r10r-paper",
        help="US30 hourly ST+PMC 2R→10R runners paper demo (OANDA prices, PaperBroker)",
    )
    demo_us30_st_pmc_2r10r_paper.add_argument("--output-root", default="")
    demo_us30_st_pmc_2r10r_paper.add_argument("--oanda-config", default="")
    demo_us30_st_pmc_2r10r_paper.add_argument("--max-ticks", type=int, default=0)
    demo_us30_st_pmc_2r10r_paper.add_argument("--daemon", action="store_true")
    demo_us30_st_pmc_2r10r_paper.set_defaults(func=cmd_demo_us30_hourly_st_pmc_2r10r_paper)

    demo_us30_st_pmc_2r10r_paper_status = sub.add_parser(
        "demo-us30-hourly-st-pmc-2r10r-paper-status",
        help="Status of US30 ST+PMC 2R→10R paper demo",
    )
    demo_us30_st_pmc_2r10r_paper_status.add_argument("--output-root", default="")
    demo_us30_st_pmc_2r10r_paper_status.set_defaults(func=cmd_demo_us30_hourly_st_pmc_2r10r_paper_status)

    demo_us30_st_pmc_2r10r_paper_stop = sub.add_parser(
        "demo-us30-hourly-st-pmc-2r10r-paper-stop",
        help="Stop US30 ST+PMC 2R→10R paper demo",
    )
    demo_us30_st_pmc_2r10r_paper_stop.add_argument("--output-root", default="")
    demo_us30_st_pmc_2r10r_paper_stop.set_defaults(func=cmd_demo_us30_hourly_st_pmc_2r10r_paper_stop)

    demo_us30_st_pmc_2r10r_oanda = sub.add_parser(
        "demo-us30-hourly-st-pmc-2r10r-oanda",
        help="US30 hourly ST+PMC 2R→10R runners OANDA practice demo",
    )
    demo_us30_st_pmc_2r10r_oanda.add_argument("--output-root", default="")
    demo_us30_st_pmc_2r10r_oanda.add_argument("--oanda-config", default="")
    demo_us30_st_pmc_2r10r_oanda.add_argument("--max-ticks", type=int, default=0)
    demo_us30_st_pmc_2r10r_oanda.add_argument("--daemon", action="store_true")
    demo_us30_st_pmc_2r10r_oanda.set_defaults(func=cmd_demo_us30_hourly_st_pmc_2r10r_oanda)

    demo_us30_st_pmc_2r10r_oanda_status = sub.add_parser(
        "demo-us30-hourly-st-pmc-2r10r-oanda-status",
        help="Status of US30 ST+PMC 2R→10R OANDA practice demo",
    )
    demo_us30_st_pmc_2r10r_oanda_status.add_argument("--output-root", default="")
    demo_us30_st_pmc_2r10r_oanda_status.set_defaults(func=cmd_demo_us30_hourly_st_pmc_2r10r_oanda_status)

    demo_us30_st_pmc_2r10r_oanda_stop = sub.add_parser(
        "demo-us30-hourly-st-pmc-2r10r-oanda-stop",
        help="Stop US30 ST+PMC 2R→10R OANDA practice demo",
    )
    demo_us30_st_pmc_2r10r_oanda_stop.add_argument("--output-root", default="")
    demo_us30_st_pmc_2r10r_oanda_stop.set_defaults(func=cmd_demo_us30_hourly_st_pmc_2r10r_oanda_stop)

    demo_nas100_st_pmc_2r10r_paper = sub.add_parser(
        "demo-nas100-hourly-st-pmc-2r10r-paper",
        help="NAS100 hourly ST+PMC 2R→10R runners paper demo (OANDA prices, PaperBroker)",
    )
    demo_nas100_st_pmc_2r10r_paper.add_argument("--output-root", default="")
    demo_nas100_st_pmc_2r10r_paper.add_argument("--oanda-config", default="")
    demo_nas100_st_pmc_2r10r_paper.add_argument("--max-ticks", type=int, default=0)
    demo_nas100_st_pmc_2r10r_paper.add_argument("--daemon", action="store_true")
    demo_nas100_st_pmc_2r10r_paper.set_defaults(func=cmd_demo_nas100_hourly_st_pmc_2r10r_paper)

    demo_nas100_st_pmc_2r10r_paper_status = sub.add_parser(
        "demo-nas100-hourly-st-pmc-2r10r-paper-status",
        help="Status of NAS100 ST+PMC 2R→10R paper demo",
    )
    demo_nas100_st_pmc_2r10r_paper_status.add_argument("--output-root", default="")
    demo_nas100_st_pmc_2r10r_paper_status.set_defaults(func=cmd_demo_nas100_hourly_st_pmc_2r10r_paper_status)

    demo_nas100_st_pmc_2r10r_paper_stop = sub.add_parser(
        "demo-nas100-hourly-st-pmc-2r10r-paper-stop",
        help="Stop NAS100 ST+PMC 2R→10R paper demo",
    )
    demo_nas100_st_pmc_2r10r_paper_stop.add_argument("--output-root", default="")
    demo_nas100_st_pmc_2r10r_paper_stop.set_defaults(func=cmd_demo_nas100_hourly_st_pmc_2r10r_paper_stop)

    demo_nas100_st_pmc_2r10r_oanda = sub.add_parser(
        "demo-nas100-hourly-st-pmc-2r10r-oanda",
        help="NAS100 hourly ST+PMC 2R→10R runners OANDA practice demo",
    )
    demo_nas100_st_pmc_2r10r_oanda.add_argument("--output-root", default="")
    demo_nas100_st_pmc_2r10r_oanda.add_argument("--oanda-config", default="")
    demo_nas100_st_pmc_2r10r_oanda.add_argument("--max-ticks", type=int, default=0)
    demo_nas100_st_pmc_2r10r_oanda.add_argument("--daemon", action="store_true")
    demo_nas100_st_pmc_2r10r_oanda.set_defaults(func=cmd_demo_nas100_hourly_st_pmc_2r10r_oanda)

    demo_nas100_st_pmc_2r10r_oanda_status = sub.add_parser(
        "demo-nas100-hourly-st-pmc-2r10r-oanda-status",
        help="Status of NAS100 ST+PMC 2R→10R OANDA practice demo",
    )
    demo_nas100_st_pmc_2r10r_oanda_status.add_argument("--output-root", default="")
    demo_nas100_st_pmc_2r10r_oanda_status.set_defaults(func=cmd_demo_nas100_hourly_st_pmc_2r10r_oanda_status)

    demo_nas100_st_pmc_2r10r_oanda_stop = sub.add_parser(
        "demo-nas100-hourly-st-pmc-2r10r-oanda-stop",
        help="Stop NAS100 ST+PMC 2R→10R OANDA practice demo",
    )
    demo_nas100_st_pmc_2r10r_oanda_stop.add_argument("--output-root", default="")
    demo_nas100_st_pmc_2r10r_oanda_stop.set_defaults(func=cmd_demo_nas100_hourly_st_pmc_2r10r_oanda_stop)

    def _add_missed_promote_demo(name, help_text, func, status_func, stop_func):
        p = sub.add_parser(name, help=help_text)
        p.add_argument("--output-root", default="")
        p.add_argument("--oanda-config", default="")
        p.add_argument("--max-ticks", type=int, default=0)
        p.add_argument("--daemon", action="store_true")
        p.set_defaults(func=func)
        ps = sub.add_parser(name + "-status", help="Status of " + name)
        ps.add_argument("--output-root", default="")
        ps.set_defaults(func=status_func)
        pst = sub.add_parser(name + "-stop", help="Stop " + name)
        pst.add_argument("--output-root", default="")
        pst.set_defaults(func=stop_func)

    _add_missed_promote_demo(
        "demo-eurusd-hourly-st-pmc-paper",
        "EURUSD ST+PMC 3R paper demo",
        cmd_demo_eurusd_hourly_st_pmc_paper,
        cmd_demo_eurusd_hourly_st_pmc_paper_status,
        cmd_demo_eurusd_hourly_st_pmc_paper_stop,
    )
    _add_missed_promote_demo(
        "demo-eurusd-hourly-st-pmc-oanda",
        "EURUSD ST+PMC 3R OANDA practice demo",
        cmd_demo_eurusd_hourly_st_pmc_oanda,
        cmd_demo_eurusd_hourly_st_pmc_oanda_status,
        cmd_demo_eurusd_hourly_st_pmc_oanda_stop,
    )
    _add_missed_promote_demo(
        "demo-eurusd-hourly-st-pmc-2r10r-paper",
        "EURUSD ST+PMC half-size 2R runner paper",
        cmd_demo_eurusd_hourly_st_pmc_2r10r_paper,
        cmd_demo_eurusd_hourly_st_pmc_2r10r_paper_status,
        cmd_demo_eurusd_hourly_st_pmc_2r10r_paper_stop,
    )
    _add_missed_promote_demo(
        "demo-eurusd-hourly-st-pmc-2r10r-oanda",
        "EURUSD ST+PMC half-size 2R runner OANDA",
        cmd_demo_eurusd_hourly_st_pmc_2r10r_oanda,
        cmd_demo_eurusd_hourly_st_pmc_2r10r_oanda_status,
        cmd_demo_eurusd_hourly_st_pmc_2r10r_oanda_stop,
    )
    _add_missed_promote_demo(
        "demo-us30-monday-or-paper",
        "US30 Monday OR M3_S3_R2 half-size paper",
        cmd_demo_us30_monday_or_paper,
        cmd_demo_us30_monday_or_paper_status,
        cmd_demo_us30_monday_or_paper_stop,
    )
    _add_missed_promote_demo(
        "demo-us30-monday-or-oanda",
        "US30 Monday OR M3_S3_R2 half-size OANDA",
        cmd_demo_us30_monday_or_oanda,
        cmd_demo_us30_monday_or_oanda_status,
        cmd_demo_us30_monday_or_oanda_stop,
    )
    _add_missed_promote_demo(
        "demo-eurusd-monday-or-paper",
        "EURUSD Monday OR M1_S2_R2 paper-half",
        cmd_demo_eurusd_monday_or_paper,
        cmd_demo_eurusd_monday_or_paper_status,
        cmd_demo_eurusd_monday_or_paper_stop,
    )

    demo_yor_paper = sub.add_parser(
        "demo-yearly-orb-paper",
        help="Yearly ORB scaleout3 paper demo (daily bars; account -002 prices)",
    )
    demo_yor_paper.add_argument("--instrument", default="", help="AUDJPY,XAUUSD,EURUSD,XAGUSD,US30 or comma list")
    demo_yor_paper.add_argument("--all", action="store_true", help="Spawn/run all promotable yearly ORB instruments")
    demo_yor_paper.add_argument("--daemon", action="store_true")
    demo_yor_paper.add_argument("--output-root", default="")
    demo_yor_paper.add_argument("--max-polls", type=int, default=0, help="0=forever; useful for smoke")
    demo_yor_paper.set_defaults(func=cmd_demo_yearly_orb_paper)

    demo_yor_paper_status = sub.add_parser("demo-yearly-orb-paper-status", help="Status of yearly ORB paper demos")
    demo_yor_paper_status.add_argument("--output-root", default="")
    demo_yor_paper_status.set_defaults(func=cmd_demo_yearly_orb_paper_status)

    demo_yor_paper_stop = sub.add_parser("demo-yearly-orb-paper-stop", help="Stop yearly ORB paper demos")
    demo_yor_paper_stop.add_argument("--output-root", default="")
    demo_yor_paper_stop.set_defaults(func=cmd_demo_yearly_orb_paper_stop)

    demo_yor_oanda = sub.add_parser(
        "demo-yearly-orb-oanda",
        help="Yearly ORB scaleout3 OANDA practice demo (daily; account 101-002-39860312-002)",
    )
    demo_yor_oanda.add_argument("--instrument", default="", help="AUDJPY,XAUUSD,EURUSD,XAGUSD,US30 or comma list")
    demo_yor_oanda.add_argument("--all", action="store_true")
    demo_yor_oanda.add_argument("--daemon", action="store_true")
    demo_yor_oanda.add_argument("--output-root", default="")
    demo_yor_oanda.add_argument("--max-polls", type=int, default=0)
    demo_yor_oanda.set_defaults(func=cmd_demo_yearly_orb_oanda)

    demo_yor_oanda_status = sub.add_parser("demo-yearly-orb-oanda-status", help="Status of yearly ORB OANDA demos")
    demo_yor_oanda_status.add_argument("--output-root", default="")
    demo_yor_oanda_status.set_defaults(func=cmd_demo_yearly_orb_oanda_status)

    demo_yor_oanda_stop = sub.add_parser("demo-yearly-orb-oanda-stop", help="Stop yearly ORB OANDA demos")
    demo_yor_oanda_stop.add_argument("--output-root", default="")
    demo_yor_oanda_stop.set_defaults(func=cmd_demo_yearly_orb_oanda_stop)

    oanda_order_smoke = sub.add_parser(
        "oanda-practice-order-smoke",
        help="Tiny practice EURUSD market place/fill/reconcile/flatten (before enabling OANDA demos)",
    )
    oanda_order_smoke.add_argument("--oanda-config", default="")
    oanda_order_smoke.add_argument("--units", type=int, default=1, help="Practice units (default 1)")
    oanda_order_smoke.set_defaults(func=cmd_oanda_practice_order_smoke)

    oanda_sync = sub.add_parser(
        "oanda-practice-sync",
        help="Query OANDA practice account vs local *_oanda demos; optional positions.csv repair",
    )
    oanda_sync.add_argument(
        "--repair-demo-positions",
        action="store_true",
        help="Rewrite each *_oanda demo positions.csv to live focus-instrument qty only",
    )
    oanda_sync.set_defaults(func=cmd_oanda_practice_sync)

    cqg_smoke = sub.add_parser("cqg-smoke", help="Validate CQG config/session scaffolding")
    cqg_smoke.add_argument("--cqg-config", default="")
    cqg_smoke.add_argument("--instrument", default="MNQ")
    cqg_smoke.add_argument("--contract-id", default="")
    cqg_smoke.add_argument("--offline", action="store_true")
    cqg_smoke.set_defaults(func=cmd_cqg_smoke)

    cqg_feed = sub.add_parser("cqg-feed-shadow", help="Replay CQG-like JSONL events into live feed state")
    cqg_feed.add_argument("--cqg-config", default="")
    cqg_feed.add_argument("--events", default="")
    cqg_feed.set_defaults(func=cmd_cqg_feed_shadow)

    cqg_paper = sub.add_parser("cqg-paper", help="Bootstrap CQG demo/sim broker/feed state")
    cqg_paper.add_argument("--cqg-config", default="")
    cqg_paper.add_argument("--events", default="")
    cqg_paper.set_defaults(func=cmd_cqg_paper)
    return p


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
