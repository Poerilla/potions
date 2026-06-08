#!/usr/bin/env python3
"""
Cross-check the manual log's Range column (in ticks) against the backtest's
Range column (in points) for matching dates. If they disagree, the user
was using a different opening range definition than the systematic
backtest — which would explain the win-rate gap.
"""
import pandas as pd

MANUAL = '/home/tester/hsm/potions/mnq/raw/Super Trend + ICT - Openning Range.csv'
V1B    = '/home/tester/hsm/potions/mnq/mnq_orb_results_fixed.csv'

manual = pd.read_csv(MANUAL)
manual.columns = [c.strip() for c in manual.columns]
manual = manual[manual['Date'].notna() & (manual['Date'].str.match(r'\d{1,2}/\d{1,2}/\d{4}'))].copy()
manual['Date'] = pd.to_datetime(manual['Date'], format='%d/%m/%Y').dt.date
manual['Range_pts'] = manual['Range'] / 4   # ticks to points
# Per-day range from manual (should be same on multi-trade days)
manual_range = manual.groupby('Date')['Range_pts'].first()

v1b = pd.read_csv(V1B)
v1b['Date'] = pd.to_datetime(v1b['Date']).dt.date
v1b_range = v1b.groupby('Date')['Range'].first()

# Inner join on dates both sources have
both = pd.DataFrame({'manual_range_pts': manual_range,
                     'v1b_range_pts':    v1b_range}).dropna()
both['delta_pts']    = both['manual_range_pts'] - both['v1b_range_pts']
both['delta_pct']    = both['delta_pts'] / both['v1b_range_pts'] * 100
both['ratio_m_to_b'] = both['manual_range_pts'] / both['v1b_range_pts']

print(f"Compared {len(both)} dates with both sources present.\n")

print("=== Range comparison stats ===")
print(f"  Mean manual range:    {both['manual_range_pts'].mean():.2f} pts")
print(f"  Mean v1b range:       {both['v1b_range_pts'].mean():.2f} pts")
print(f"  Mean delta:           {both['delta_pts'].mean():+.2f} pts ({both['delta_pct'].mean():+.1f}%)")
print(f"  Median delta:         {both['delta_pts'].median():+.2f} pts ({both['delta_pct'].median():+.1f}%)")

# Distribution of % delta
print(f"\n  % delta distribution (manual vs v1b range):")
for p in (0.05, 0.25, 0.5, 0.75, 0.95):
    print(f"    P{int(p*100):>3}: {both['delta_pct'].quantile(p):+.1f}%")

# Match buckets
exact = (both['delta_pts'].abs() <= 1).sum()
within_5pct = (both['delta_pct'].abs() <= 5).sum()
within_15pct = (both['delta_pct'].abs() <= 15).sum()
much_diff = (both['delta_pct'].abs() > 30).sum()
print(f"\n  Exact match (within 1 pt): {exact}/{len(both)} ({exact/len(both)*100:.1f}%)")
print(f"  Within ±5%:                {within_5pct}/{len(both)} ({within_5pct/len(both)*100:.1f}%)")
print(f"  Within ±15%:               {within_15pct}/{len(both)} ({within_15pct/len(both)*100:.1f}%)")
print(f"  > ±30% differ:             {much_diff}/{len(both)} ({much_diff/len(both)*100:.1f}%)")

# Show a sample of biggest discrepancies
print(f"\n=== 15 days with biggest range delta (where they disagree most) ===")
top = both.copy()
top['abs_delta_pct'] = top['delta_pct'].abs()
top = top.sort_values('abs_delta_pct', ascending=False).head(15)
print(f"{'Date':>12} {'Manual':>8} {'v1b':>8} {'Δ pts':>8} {'Δ %':>7}")
for d, r in top.iterrows():
    print(f"{str(d):>12} {r['manual_range_pts']:>8.2f} {r['v1b_range_pts']:>8.2f} "
          f"{r['delta_pts']:>+8.2f} {r['delta_pct']:>+6.1f}%")

# And a sample of close matches
print(f"\n=== 10 days with closest range match ===")
top_match = both.copy()
top_match['abs_delta_pct'] = top_match['delta_pct'].abs()
top_match = top_match.sort_values('abs_delta_pct').head(10)
for d, r in top_match.iterrows():
    print(f"{str(d):>12} {r['manual_range_pts']:>8.2f} {r['v1b_range_pts']:>8.2f} "
          f"{r['delta_pts']:>+8.2f} {r['delta_pct']:>+6.1f}%")
