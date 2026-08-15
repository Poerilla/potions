"""Regression tests for banked reporting, rankable boards, and regime classes."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from live.exit_attribution import attribute_rows, candidate_status_gates
from live.hub_snapshot import (
    LABEL_INCOMPLETE,
    LABEL_INSUFFICIENT,
    LABEL_PENDING_ACCT,
    LABEL_PENDING_NORM,
    LABEL_RESEARCH,
    LABEL_RETAIN,
    STATUS_COMPLETE,
    STATUS_IN_PROGRESS,
    STATUS_PARTIAL,
    _partition_boards,
    compare_snapshots,
    evaluate_row_eligibility,
    render_email,
    write_snapshot_artifacts,
)
from live.regime_overlap import (
    CLASS_CONDITIONAL,
    CLASS_SAME,
    CLASS_SEPARATE,
    CLASS_UNRESOLVED,
    book_identity,
    classify_regime_overlap,
    duplicate_sleeve_warnings,
    overlap_metrics,
)


class RegimeOverlapTests(unittest.TestCase):
    def test_low_jaccard_high_corr_is_conditional_not_separate(self):
        # YM PO vs US30 PO style: sparse co-occurrence, high shared-day relationship
        out = classify_regime_overlap(
            day_jaccard=0.128,
            dir_agree_rate_on_shared=0.986,
            shared_day_pnl_corr=0.549,
            shared_days=71,
            corr_days=71,
            a_campaigns=436,
            b_campaigns=309,
        )
        self.assertEqual(out["regime_class"], CLASS_CONDITIONAL)
        self.assertFalse(out["regime_separable"])

    def test_legacy_or_rule_would_misclassify_conditional(self):
        jacc, rho = 0.128, 0.549
        legacy_separable = jacc < 0.35 or abs(rho) < 0.25
        self.assertTrue(legacy_separable)  # the bug
        out = classify_regime_overlap(
            day_jaccard=jacc,
            dir_agree_rate_on_shared=0.986,
            shared_day_pnl_corr=rho,
            shared_days=71,
            corr_days=71,
            a_campaigns=100,
            b_campaigns=100,
        )
        self.assertEqual(out["regime_class"], CLASS_CONDITIONAL)

    def test_ym_us30_stpmc_same_sleeve(self):
        out = classify_regime_overlap(
            day_jaccard=0.423,
            dir_agree_rate_on_shared=0.998,
            shared_day_pnl_corr=0.851,
            shared_days=417,
            corr_days=417,
            a_campaigns=985,
            b_campaigns=578,
        )
        self.assertEqual(out["regime_class"], CLASS_SAME)

    def test_separate_regimes_low_overlap_low_corr(self):
        out = classify_regime_overlap(
            day_jaccard=0.05,
            dir_agree_rate_on_shared=0.10,
            shared_day_pnl_corr=0.004,
            shared_days=52,
            corr_days=52,
            a_campaigns=200,
            b_campaigns=200,
        )
        self.assertEqual(out["regime_class"], CLASS_SEPARATE)

    def test_unresolved_small_sample(self):
        out = classify_regime_overlap(
            day_jaccard=0.1,
            dir_agree_rate_on_shared=0.9,
            shared_day_pnl_corr=0.8,
            shared_days=3,
            corr_days=3,
            a_campaigns=5,
            b_campaigns=5,
        )
        self.assertEqual(out["regime_class"], CLASS_UNRESOLVED)

    def test_exact_book_identity_in_overlap_result(self):
        camps_a = [
            {"day": "2020-01-0%d" % i, "dir": "L", "net_usd": 1.0} for i in range(1, 9)
        ] + [
            {"day": "2020-02-0%d" % i, "dir": "L", "net_usd": -1.0} for i in range(1, 9)
        ]
        camps_b = [
            {"day": "2020-01-0%d" % i, "dir": "L", "net_usd": 1.2} for i in range(1, 9)
        ] + [
            {"day": "2020-03-0%d" % i, "dir": "S", "net_usd": 0.5} for i in range(1, 9)
        ]
        ia = book_identity(
            market="ym",
            strategy="st_pmc",
            book="sl50_tp150_3r_1mfill",
            strategy_id="ym_hourly_st_pmc_sl50_tp150_3r_1mfill",
        )
        ib = book_identity(
            market="us30",
            strategy="st_pmc",
            book="sl50_tp150_3r_1mfill",
            strategy_id="us30_hourly_st_pmc_sl50_tp150_3r_1mfill",
        )
        out = overlap_metrics("a", camps_a, "b", camps_b, identity_a=ia, identity_b=ib)
        self.assertEqual(out["identity_a"]["strategy_id"], ia["strategy_id"])
        self.assertEqual(out["identity_b"]["book"], "sl50_tp150_3r_1mfill")
        self.assertIn("regime_class", out)
        self.assertIn("union_day_pnl_corr", out)

    def test_nq_mnq_duplicate_sleeve_warning(self):
        warns = duplicate_sleeve_warnings(["nq", "mnq"], strategy="st_pmc", book="3r")
        self.assertTrue(warns)
        self.assertEqual(warns[0]["warning"], "DUPLICATE_EXECUTION_SLEEVE")
        self.assertIn("Nasdaq", warns[0]["message"])


class RankableBoardTests(unittest.TestCase):
    def test_native_jpy_cannot_enter_usd_board(self):
        ev = evaluate_row_eligibility(
            {
                "units": 851,
                "net_usd": 9_000_000,
                "stress_dd_usd": -1_000_000,
                "ns": 7.8,
                "eoy_flatten_units": 0,
                "wr_pct": 30,
                "max_open": 1,
                "notes": "reachable",
            },
            market="audjpy",
            variant="sl50_tp150_3r_1mfill",
            audit_ok=True,
            usd_norm=None,
            lot_correct=None,
        )
        self.assertFalse(ev["comparable_core_eligible"])
        self.assertEqual(ev["decision_label"], LABEL_PENDING_NORM)
        self.assertIn("native_jpy_not_usd_normalized", ev["exclusion_reasons"])

    def test_insufficient_sample_not_rankable(self):
        ev = evaluate_row_eligibility(
            {
                "units": 1,
                "net_usd": 100,
                "stress_dd_usd": -50,
                "ns": 2.0,
                "eoy_flatten_units": 0,
                "wr_pct": 100,
                "max_open": 1,
                "notes": "reachable",
            },
            market="xagusd",
            variant="sl50_tp150_3r_1mfill",
            audit_ok=True,
            usd_norm=None,
            lot_correct=None,
        )
        self.assertFalse(ev["comparable_core_eligible"])
        self.assertEqual(ev["decision_label"], LABEL_INSUFFICIENT)

    def test_indefinite_cannot_enter_flat_board(self):
        ev = evaluate_row_eligibility(
            {
                "units": 200,
                "net_usd": 1000,
                "stress_dd_usd": -500,
                "ns": 2.0,
                "eoy_flatten_units": 48,
                "wr_pct": 20,
                "max_open": 100,
                "notes": "reachable",
            },
            market="eurusd",
            variant="sl50_tp150_runners_2r_indef",
            audit_ok=True,
            usd_norm=None,
            lot_correct={
                "forced_flat_equity_usd": 900,
                "continuous_terminal_equity_usd": 950,
                "reachable_stress_dd_usd": -400,
                "raw_intrabar_stress_dd_usd": -800,
                "ns_forced_flat_reachable": 2.25,
                "max_open_units": 100,
                "open_lots_terminal": 40,
                "max_gross_notional": 1e6,
            },
        )
        self.assertFalse(ev["comparable_core_eligible"])
        self.assertEqual(ev["decision_label"], LABEL_RESEARCH)
        self.assertIn("indefinite_inventory_not_rankable_vs_flat_books", ev["exclusion_reasons"])

    def test_lot_correct_reachable_overrides_raw(self):
        ev = evaluate_row_eligibility(
            {
                "units": 200,
                "net_usd": 1000,
                "stress_dd_usd": -900,  # raw archive
                "ns": 1.1,
                "eoy_flatten_units": 0,
                "wr_pct": 30,
                "max_open": 1,
                "notes": "",
            },
            market="us30",
            variant="sl50_tp150_3r_1mfill",
            audit_ok=True,
            usd_norm=None,
            lot_correct={
                "forced_flat_equity_usd": 19028,
                "continuous_terminal_equity_usd": 19028,
                "reachable_stress_dd_usd": -647,
                "raw_intrabar_stress_dd_usd": -907,
                "ns_forced_flat_reachable": 29.389,
                "max_open_units": 1,
                "open_lots_terminal": 0,
                "max_gross_notional": 45000,
            },
        )
        self.assertTrue(ev["comparable_core_eligible"])
        self.assertEqual(ev["metrics"]["metric_source"], "LOT_CORRECT_ACCOUNTING.csv")
        self.assertEqual(ev["metrics"]["stress_dd_usd"], -647)
        self.assertNotEqual(ev["metrics"]["stress_dd_usd"], ev["metrics"]["raw_stress_dd_usd"])
        self.assertIn("raw_intrabar_stress_superseded_by_reachable", ev["accounting_warnings"])

    def test_usd_normalized_jpy_3r_can_enter_board(self):
        ev = evaluate_row_eligibility(
            {
                "units": 869,
                "net_usd": 4_040_011,
                "stress_dd_usd": -2_282_415,
                "ns": 1.77,
                "eoy_flatten_units": 0,
                "wr_pct": 27.5,
                "max_open": 1,
                "notes": "reachable",
            },
            market="usdjpy",
            variant="sl50_tp150_3r_1mfill",
            audit_ok=True,
            usd_norm={"net_usd": 30407, "stress_dd_usd": -19540, "ns": 1.56},
            lot_correct=None,
        )
        self.assertTrue(ev["comparable_core_eligible"])
        self.assertEqual(ev["metrics"]["net_usd"], 30407)
        self.assertEqual(ev["metrics"]["metric_source"], "FAIR_3R_USD_NORMALIZED.md")

    def test_retain_appears_on_tested_not_promoted_board(self):
        retain = evaluate_row_eligibility(
            {
                "units": 100,
                "net_usd": 1000,
                "stress_dd_usd": -100,
                "ns": 10.0,
                "eoy_flatten_units": 0,
                "wr_pct": 40,
                "max_open": 1,
                "notes": "reachable",
            },
            market="eurusd",
            variant="sl50_tp150_3r_1mfill",
            audit_ok=True,
            usd_norm=None,
            lot_correct=None,
        )
        self.assertEqual(retain["decision_label"], LABEL_RETAIN)
        boards = _partition_boards([retain])
        self.assertTrue(boards["comparable_core_board"]["rankable"])
        self.assertEqual(len(boards["tested_not_promoted"]["rows"]), 1)
        self.assertFalse(boards["tested_not_promoted"]["rankable"])


class SnapshotEmailTests(unittest.TestCase):
    def _snap(self, **kwargs):
        base = {
            "hub": "live/state/test_hub",
            "status": STATUS_PARTIAL,
            "complete": False,
            "generated_at_utc": "2026-08-09T12:00:00+00:00",
            "completed_required_jobs": 2,
            "total_required_jobs": 6,
            "accounting_mode": "lot-correct-preferred",
            "active_jobs": [
                {
                    "market": "audjpy",
                    "variant": "sl50_tp150_runners_2r_indef",
                    "status": "running",
                    "progress": "indef 105000/139327 (75%)",
                    "pid": 12345,
                    "command": "python -m live.fx_index_metals_st_pmc_runner_variants --markets audjpy",
                }
            ],
            "incomplete_jobs": [
                {"market": "xauusd", "variant": "sl50_tp150_runners_2r_10r", "reason": "missing_from_summary"}
            ],
            "decision_summary": {LABEL_INCOMPLETE: ["XAUUSD 2R→10R"]},
            "blocks_final_judgment": ["hub_status=PARTIAL", "1_active_jobs"],
            "portfolio_action_required": {"required": True, "actions": ["No final promotion"]},
            "change_since_prior_snapshot": [
                "+ EURUSD 2R→10R and indefinite completed",
                "= No new promoted strategy",
                "! AUDJPY runner variants still active",
            ],
            "boards": {
                "comparable_core_board": {"title": "Comparable Core Board", "rankable": True, "rows": []},
                "tested_not_promoted": {"title": "Tested", "rankable": False, "rows": []},
                "pending_non_comparable": {"title": "Pending", "rankable": False, "rows": []},
                "indefinite_inventory_research": {
                    "title": "INDEFINITE INVENTORY RESEARCH — NOT RANKABLE",
                    "rankable": False,
                    "rows": [],
                },
            },
            "duplicate_sleeve_warnings": [],
        }
        base.update(kwargs)
        return base

    def test_complete_false_cannot_produce_completion_report_title(self):
        body = render_email(self._snap(complete=False, status=STATUS_PARTIAL))
        self.assertNotIn("COMPLETION REPORT", body.splitlines()[0])
        self.assertTrue(
            body.startswith("INTERIM SNAPSHOT") or body.startswith("IN PROGRESS")
        )

    def test_in_progress_title(self):
        body = render_email(self._snap(status=STATUS_IN_PROGRESS, complete=False))
        self.assertTrue(body.startswith("IN PROGRESS SNAPSHOT"))

    def test_true_completion_title_only_when_complete(self):
        body = render_email(self._snap(status=STATUS_COMPLETE, complete=True, active_jobs=[], incomplete_jobs=[]))
        self.assertTrue(body.startswith("COMPLETION REPORT"))

    def test_active_and_incomplete_jobs_shown_without_raw_commands(self):
        body = render_email(self._snap())
        self.assertIn("Active jobs: 1", body)
        self.assertIn("AUDJPY:", body)
        self.assertIn("Incomplete jobs:", body)
        self.assertNotIn("python -m live.fx_index_metals", body)
        self.assertNotIn("pid=12345", body)
        self.assertIn("CHANGE SINCE PRIOR SNAPSHOT", body)

    def test_compare_snapshots_change_lines(self):
        prior = {
            "status": STATUS_IN_PROGRESS,
            "evaluations": [
                {
                    "market": "eurusd",
                    "variant": "sl50_tp150_3r_1mfill",
                    "audit_ok": True,
                    "metrics": {"units": 10},
                }
            ],
            "decision_summary": {"PROMOTE": []},
            "active_jobs": [],
        }
        current = {
            "status": STATUS_PARTIAL,
            "evaluations": [
                {
                    "market": "eurusd",
                    "variant": "sl50_tp150_3r_1mfill",
                    "audit_ok": True,
                    "metrics": {"units": 10},
                },
                {
                    "market": "eurusd",
                    "variant": "sl50_tp150_runners_2r_10r",
                    "audit_ok": True,
                    "metrics": {"units": 20},
                },
                {
                    "market": "eurusd",
                    "variant": "sl50_tp150_runners_2r_indef",
                    "audit_ok": True,
                    "metrics": {"units": 30},
                },
            ],
            "decision_summary": {"PROMOTE": []},
            "active_jobs": [{"market": "audjpy", "variant": "indef"}],
        }
        lines = compare_snapshots(prior, current)
        self.assertTrue(any("EURUSD" in ln and "completed" in ln for ln in lines))
        self.assertTrue(any("No new promoted" in ln for ln in lines))
        self.assertTrue(any("AUDJPY" in ln and "active" in ln for ln in lines))

    def test_indefinite_raw_not_labeled_forced_flat_in_email(self):
        ev = evaluate_row_eligibility(
            {
                "units": 200,
                "net_usd": 339774,
                "stress_dd_usd": -228428,
                "ns": 1.5,
                "eoy_flatten_units": 48,
                "wr_pct": 20,
                "max_open": 239,
                "notes": "reachable",
            },
            market="eurusd",
            variant="sl50_tp150_runners_2r_indef",
            audit_ok=True,
            usd_norm=None,
            lot_correct=None,
        )
        self.assertIsNone(ev["metrics"]["forced_flat_net_pnl"])
        self.assertFalse(ev["metrics"]["lot_correct_available"])
        self.assertEqual(ev["decision_label"], LABEL_PENDING_ACCT)
        body = render_email(
            self._snap(
                boards={
                    "comparable_core_board": {
                        "title": "Comparable Core Board",
                        "rankable": False,
                        "rows": [],
                    },
                    "tested_not_promoted": {"title": "Tested", "rankable": False, "rows": []},
                    "pending_non_comparable": {"title": "Pending", "rankable": False, "rows": []},
                    "indefinite_inventory_research": {
                        "title": "INDEFINITE INVENTORY RESEARCH — NOT RANKABLE",
                        "rankable": False,
                        "rows": [ev],
                    },
                }
            )
        )
        self.assertIn("forced-flat=pending", body)
        self.assertIn("raw/archive (not forced-flat)", body)
        self.assertNotIn("forced-flat=$339.8k", body)

    def test_parse_mtm_audit_synthesis(self):
        from live.hub_snapshot import _parse_mtm_audit

        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "MTM_AUDIT.md"
            p.write_text(
                "\n".join(
                    [
                        "| Units | 942 |",
                        "| Winning units | 158 |",
                        "| Losing units | 784 |",
                        "| Net dollars | $9,825,893.32 |",
                        "| Intrabar stress MTM DD | $-4,798,863.80 |",
                        "| Max open units | 3 |",
                        "| Net / intrabar stress DD | 2.05 |",
                        "",
                        "Notes: forced_flat_open=0 @ end.",
                    ]
                ),
                encoding="utf-8",
            )
            row = _parse_mtm_audit(p)
            self.assertEqual(row["units"], 942)
            self.assertAlmostEqual(row["net_usd"], 9825893.32)
            self.assertAlmostEqual(row["ns"], 2.05)
            self.assertEqual(row["eoy_flatten_units"], 0)

    def test_write_artifacts(self):
        snap = self._snap(status=STATUS_IN_PROGRESS, complete=False)
        with tempfile.TemporaryDirectory() as td:
            hub = Path(td)
            paths = write_snapshot_artifacts(hub, snap, email=False)
            self.assertTrue(paths["latest_snapshot"].exists())
            self.assertTrue(paths["email"].exists())
            self.assertTrue(paths["report"].exists())
            self.assertTrue(paths["changelog"].exists())
            email = paths["email"].read_text()
            self.assertTrue(email.startswith("IN PROGRESS"))
            data = json.loads(paths["latest_snapshot"].read_text())
            self.assertEqual(data["status"], STATUS_IN_PROGRESS)


class ExitAttributionTests(unittest.TestCase):
    def test_eod_survivor_label_not_10r_moonshot(self):
        rows = []
        for i in range(100):
            rows.append({"trade_id": "t%d" % i, "exit_reason": "eod_close", "net_usd": 50})
            rows.append({"trade_id": "t%d" % i, "exit_reason": "runner_stop", "net_usd": 5})
            rows.append({"trade_id": "t%d" % i, "exit_reason": "tp1", "net_usd": 10})
        rows.append({"trade_id": "rare", "exit_reason": "runner_tp", "net_usd": 20})
        out = attribute_rows(rows, strategy_id="nq_plus_1x10R")
        self.assertFalse(out["is_10r_moonshot"])
        self.assertTrue(out["eod_survivor_dominant"])
        self.assertIn("EOD-survivor", out["book_label"])
        self.assertIn("BE-protected", out["book_label"])

    def test_candidate_gates(self):
        g = candidate_status_gates(
            full_stack_reachable_stress=True,
            lot_correct=True,
            open_inventory_reported=True,
            margin_reported=True,
            exact_book_regime_overlap=True,
            causality_violations=0,
            sufficient_sample=True,
        )
        self.assertTrue(g["candidate_ready"])
        g2 = candidate_status_gates(
            full_stack_reachable_stress=False,
            lot_correct=False,
            open_inventory_reported=False,
            margin_reported=False,
            exact_book_regime_overlap=False,
            causality_violations=2,
            sufficient_sample=False,
        )
        self.assertFalse(g2["candidate_ready"])
        self.assertGreaterEqual(len(g2["failed_gates"]), 5)


if __name__ == "__main__":
    unittest.main()
