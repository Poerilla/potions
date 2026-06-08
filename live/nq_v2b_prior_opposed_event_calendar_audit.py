from __future__ import annotations

import argparse
import html
import re
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional, Set

import pandas as pd
import requests

from .nq_v2b_prior_opposed_replay import PRIOR_OPPOSED_MARKETS
from .nq_v2b_prior_opposed_filter_study import apply_scenario, build_trade_unit_matrix


REPO = Path(__file__).resolve().parents[1]
FED_FOMC_URL = "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"
BLS_CPI_ARCHIVE_URL = "https://www.bls.gov/bls/news-release/cpi.htm"

MONTHS = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}


def _get(url: str) -> str:
    r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
    r.raise_for_status()
    return r.text


def parse_fomc_dates(html_text: str, start_year: int, end_year: int) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    year_positions = [(int(m.group(1)), m.start()) for m in re.finditer(r">(\d{4}) FOMC Meetings<", html_text)]
    year_positions.sort(key=lambda item: item[1])
    for idx, (year, pos) in enumerate(year_positions):
        if year < start_year or year > end_year:
            continue
        end = year_positions[idx + 1][1] if idx + 1 < len(year_positions) else len(html_text)
        section = html_text[pos:end]
        pattern = re.compile(
            r'fomc-meeting__month[^>]*>\s*<strong>(.*?)</strong>.*?'
            r'fomc-meeting__date[^>]*>(.*?)</div>',
            re.S | re.I,
        )
        for month_raw, date_raw in pattern.findall(section):
            month_text = re.sub(r"<.*?>", "", html.unescape(month_raw)).strip().lower()
            date_text = re.sub(r"<.*?>", "", html.unescape(date_raw)).strip()
            if not month_text or not date_text:
                continue
            month_parts = [p.strip().lower() for p in re.split(r"/| and ", month_text) if p.strip()]
            month_name = month_parts[-1]
            if month_name not in MONTHS:
                continue
            nums = [int(x) for x in re.findall(r"\d+", date_text)]
            if not nums:
                continue
            day = nums[-1]
            month = MONTHS[month_name]
            # Handle "Dec/Jan" year-crossing style ranges if ever present.
            event_year = year
            if len(month_parts) > 1 and month_name == "january" and "december" in month_parts[0]:
                event_year = year + 1
            try:
                event_date = date(event_year, month, day)
            except ValueError:
                continue
            rows.append(
                {
                    "date": event_date.isoformat(),
                    "event_type": "FOMC",
                    "source": FED_FOMC_URL,
                    "description": "%s %s FOMC decision day" % (month_text.title(), date_text),
                }
            )
    return rows


def parse_cpi_dates(html_text: str, start_year: int, end_year: int) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    seen: Set[date] = set()
    for mmddyyyy in re.findall(r"archives/cpi_(\d{8})", html_text):
        month = int(mmddyyyy[:2])
        day = int(mmddyyyy[2:4])
        year = int(mmddyyyy[4:])
        if year < start_year or year > end_year:
            continue
        try:
            event_date = date(year, month, day)
        except ValueError:
            continue
        if event_date in seen:
            continue
        seen.add(event_date)
        rows.append(
            {
                "date": event_date.isoformat(),
                "event_type": "CPI",
                "source": BLS_CPI_ARCHIVE_URL,
                "description": "CPI news release archive link cpi_%s" % mmddyyyy,
            }
        )
    rows.sort(key=lambda item: item["date"])
    return rows


def build_calendar(output_root: Path, start_year: int, end_year: int) -> pd.DataFrame:
    fomc = parse_fomc_dates(_get(FED_FOMC_URL), start_year, end_year)
    cpi = parse_cpi_dates(_get(BLS_CPI_ARCHIVE_URL), start_year, end_year)
    events = pd.DataFrame(fomc + cpi).drop_duplicates(["date", "event_type"]).sort_values(["date", "event_type"])
    events.to_csv(output_root / "event_calendar.csv", index=False)
    return events


def run_event_scenarios(audit_root: Path, state_root: Path, events: pd.DataFrame) -> pd.DataFrame:
    campaigns_path = audit_root / "campaigns_with_sizing.csv"
    if campaigns_path.exists():
        base = pd.read_csv(campaigns_path, parse_dates=["entry_ts", "exit_ts"])
    else:
        campaigns = pd.read_csv(audit_root / "campaigns_robustness.csv", parse_dates=["entry_ts", "exit_ts"])
        units = pd.read_csv(state_root / "unit_trades.csv")
        base = build_trade_unit_matrix(campaigns, units)

    all_events = set(events["date"].astype(str))
    fomc = set(events[events["event_type"].eq("FOMC")]["date"].astype(str))
    cpi = set(events[events["event_type"].eq("CPI")]["date"].astype(str))

    scenarios = [
        apply_scenario(base, "base_1_1_3", lambda row: "1_1_3"),
        apply_scenario(base, "skip_all_event_days", lambda row: "1_1_3", lambda row: str(row["session"]) not in all_events),
        apply_scenario(base, "event_days_to_1_1_1", lambda row: "1_1_1" if str(row["session"]) in all_events else "1_1_3"),
        apply_scenario(base, "event_days_to_1_1_0", lambda row: "1_1_0" if str(row["session"]) in all_events else "1_1_3"),
        apply_scenario(base, "skip_fomc_days", lambda row: "1_1_3", lambda row: str(row["session"]) not in fomc),
        apply_scenario(base, "fomc_days_to_1_1_1", lambda row: "1_1_1" if str(row["session"]) in fomc else "1_1_3"),
        apply_scenario(base, "skip_cpi_days", lambda row: "1_1_3", lambda row: str(row["session"]) not in cpi),
        apply_scenario(base, "cpi_days_to_1_1_1", lambda row: "1_1_1" if str(row["session"]) in cpi else "1_1_3"),
        apply_scenario(
            base,
            "skip_fomc_after_1330",
            lambda row: "1_1_3",
            lambda row: str(row["session"]) not in fomc or pd.Timestamp(row["entry_ts"]).time() < pd.Timestamp("13:30").time(),
        ),
    ]
    out = pd.DataFrame(scenarios).sort_values("net_over_stress", ascending=False)
    out.to_csv(audit_root / "event_scenario_matrix.csv", index=False)
    event_campaigns = base[base["session"].astype(str).isin(all_events)].copy()
    event_campaigns.to_csv(audit_root / "campaigns_on_event_days.csv", index=False)
    return out


def write_report(output_root: Path, events: pd.DataFrame, scenarios: pd.DataFrame, instrument: str) -> None:
    lines = [
        "# %s Prior-Opposed v2b Event Calendar Audit" % instrument,
        "",
        "Event dates are pulled from free official sources:",
        "",
        f"- Federal Reserve FOMC meeting calendar: {FED_FOMC_URL}",
        f"- BLS CPI archived news releases: {BLS_CPI_ARCHIVE_URL}",
        "",
        "FOMC dates use the final meeting day / decision day. CPI dates use BLS archived release dates.",
        "",
        "## Event Counts",
        "",
        events.groupby("event_type").size().reset_index(name="count").to_markdown(index=False),
        "",
        "## Scenario Matrix",
        "",
        scenarios.to_markdown(index=False, floatfmt=".2f"),
        "",
        "## Read",
        "",
    ]
    base = scenarios[scenarios["scenario"].eq("base_1_1_3")].iloc[0]
    best = scenarios.sort_values("net_over_stress", ascending=False).iloc[0]
    lines += [
        "- Best event-calendar row: **%s** at %.2f Net/Stress versus base %.2f."
        % (best["scenario"], float(best["net_over_stress"]), float(base["net_over_stress"])),
        "- Treat this as a first-pass date audit only; CPI/FOMC labels do not include surprise magnitude, press conference windows, or other macro releases.",
        "",
        "## Files",
        "",
        "- `event_calendar.csv`",
        "- `event_scenario_matrix.csv`",
        "- `campaigns_on_event_days.csv`",
    ]
    (output_root / "EVENT_CALENDAR_AUDIT.md").write_text("\n".join(lines))


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="CPI/FOMC event-date audit for prior-opposed v2b.")
    parser.add_argument("--market", choices=PRIOR_OPPOSED_MARKETS, default="nq")
    parser.add_argument(
        "--audit-root",
        type=Path,
        default=None,
    )
    parser.add_argument(
        "--state-root",
        type=Path,
        default=None,
    )
    parser.add_argument("--start-year", type=int, default=2021)
    parser.add_argument("--end-year", type=int, default=2026)
    args = parser.parse_args(argv)
    market = args.market.lower()
    instrument = market.upper()
    audit_root = args.audit_root or REPO / f"live/state/{market}_v2b_prior_opposed_stpmc_broker_like/robustness_audit"
    state_root = args.state_root or REPO / f"live/state/{market}_v2b_prior_opposed_stpmc_broker_like/states/{market}_v2b_prior_opposed_stpmc_only_S_1_1_3"
    audit_root.mkdir(parents=True, exist_ok=True)
    events = build_calendar(audit_root, args.start_year, args.end_year)
    scenarios = run_event_scenarios(audit_root, state_root, events)
    write_report(audit_root, events, scenarios, instrument)
    print("Wrote %s" % (audit_root / "EVENT_CALENDAR_AUDIT.md"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
