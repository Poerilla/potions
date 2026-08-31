NQ WICK-REJECT -> NY OPEN -> 1M PROTECTED-PIVOT STUDY PLAN (V1)

STUDY ID
nq_wick_reject_4h_ny_open_1m_protected_pivot_v1

INSTRUMENT
NQ

STATUS
RESEARCH / DESCRIPTIVE ONLY

PURPOSE
After a completed and active 4-hour WICK_REJECT seed, identify a qualifying
New York open 1-minute reversal structure. Test whether its designated pivot
becomes structurally protected for a fixed post-formation observation
horizon.

This is not an entry system. It does not create a trade, P&L, stop, target,
position size, plugin, or promotion decision.

NON-GOALS
- No live signal.
- No entry, stop, target, or position-sizing rules.
- No optimization after outcome review.
- No combination with S1 seed-boundary model.
- No combination with S2 new-swing model.
- No S1/S2/this-model chooser.
- No plugin, paper-trading, or live-trading promotion from this study alone.


1. TIME AND SESSION DEFINITIONS

TIMEZONE
Use America/New_York for every timestamp. Do not use a fixed UTC offset.
Timezone conversion must handle daylight saving time.

NY OPEN
NY_OPEN_TS = 09:30:00 America/New_York on the relevant trading date.

FORMATION WINDOW
OPEN_WINDOW_START = 09:30:00 ET
OPEN_WINDOW_END = 10:30:00 ET

A qualifying four-pivot structure must have its final pivot causally
confirmed
by 10:30 ET.

PROTECTION HORIZON
OBSERVATION_END = 13:00:00 ET on the same NY trading date.

The structure is observed, not traded, from final causal confirmation
through
13:00 ET.

ONE NY OPEN PER 4H SEED
For V1, evaluate only the first eligible NY open after each 4-hour seed
becomes
available. Do not create multiple daily samples from one seed.


2. 4-HOUR WICK-REJECT SEED INPUT

Use the existing 4-hour WICK_REJECT seed ledger. This study consumes its
seed
records and does not alter the existing wick-reject rules.

REQUIRED SEED FIELDS
seed_id
seed_ts
seed_available_at
seed_high
seed_low
seed_width
seed_direction
seed_expiry
seed_active
range_width_atr
penetration_atr

FIELD DEFINITIONS

seed_id:
Unique ID of the completed 4-hour WICK_REJECT event.

seed_ts:
Timestamp of the completed 4-hour wick-reject candle close.

seed_available_at:
First valid 1-minute timestamp after the 4-hour candle has completed.
No lower-timeframe event may use this seed before this time.

seed_high:
High of the completed 4-hour wick-reject candle.

seed_low:
Low of the completed 4-hour wick-reject candle.

seed_width:
seed_high minus seed_low.

seed_direction:
Direction classification of the original 4-hour wick rejection.
Keep it as context only. It does not determine whether the later 1-minute
sequence must be bullish or bearish.

seed_expiry:
The last timestamp for which the seed is valid under the existing seed
policy.

seed_active:
True if the seed is valid and unexpired.

range_width_atr:
seed_width normalized by 4-hour ATR.

penetration_atr:
How far the wick passed beyond the swept 4-hour structural level, normalized
by 4-hour ATR.

NY-OPEN SEED ELIGIBILITY

A seed is eligible only if all of the following are true:

1. NY_OPEN_TS is at or after seed_available_at.
2. The seed remains active at NY_OPEN_TS.
3. The session is not excluded for a holiday, early close, or documented
   calendar reason.
4. Complete 1-minute OHLC data exist from 09:30 through 13:00 ET.
5. It is the first eligible NY open assigned to the seed.

REQUIRED EXCLUSION REASONS

before_seed_available
expired_or_inactive_seed
holiday
early_close
missing_1m_data
duplicate_seed_assignment
other_documented_data_exception


3. 1-MINUTE PIVOT ENGINE

TIMEFRAME
All pivots use completed 1-minute NQ OHLC bars.

V1 PIVOT RULE

Use strict three-bar pivots:

Pivot high at bar t:
high[t] > high[t-1]
and
high[t] > high[t+1]

Pivot low at bar t:
low[t] < low[t-1]
and
low[t] < low[t+1]

Equal highs and equal lows do not count as pivots in V1.

PIVOT PARAMETERS

pivot_left_bars = 1
pivot_right_bars = 1
strict_extrema = true
equal_level_policy = reject
min_pivot_separation_bars = 1

CAUSALITY

pivot_ts:
The close time of the candidate pivot candle.

pivot_available_at:
The close time of the confirming right-side candle.

Example:

A possible swing high occurs on 09:35 candle.
It cannot be used at 09:35.
It only becomes confirmed at the close of the 09:36 candle.

Therefore:

pivot_ts = 09:35
pivot_available_at = 09:36

A four-pivot structure cannot be counted until P4 is confirmed.

REQUIRED 1-MINUTE PIVOT LEDGER FIELDS

seed_id
ny_date
pivot_id
pivot_type
pivot_price
pivot_ts
pivot_available_at
bar_index_from_open
inside_open_window
left_bars
right_bars
strict_extrema


4. FOUR-PIVOT STRUCTURES

There are two formation structures.

A. BEARISH STRUCTURE

Sequence:

P1 = H1
P2 = L1
P3 = HH
P4 = LL

Required order:

H1 -> L1 -> Higher High -> Lower Low

Required price relationships:

HH > H1
LL < L1

All four pivots must occur after 09:30 ET.
P4 must be causally confirmed by 10:30 ET.

Once P4 is confirmed:

- The bearish structure is complete.
- P3 / HH becomes the candidate protected high.
- P2 / L1 is the downside break level.
- The lower low shows that price broke below the previous low while the
higher
  high remained intact.

Bearish example:

09:32 P1 / H1 = 20,100.00
09:37 P2 / L1 = 20,080.00
09:43 P3 / HH = 20,108.00
09:51 P4 / LL = 20,074.00

This is a valid bearish pattern because:

20,108.00 > 20,100.00
20,074.00 < 20,080.00

The 20,108.00 HH is the candidate protected high.

B. BULLISH STRUCTURE

Sequence:

P1 = L1
P2 = H1
P3 = LL
P4 = HH

Required order:

L1 -> H1 -> Lower Low -> Higher High

Required price relationships:

LL < L1
HH > H1

All four pivots must occur after 09:30 ET.
P4 must be causally confirmed by 10:30 ET.

Once P4 is confirmed:

- The bullish structure is complete.
- P3 / LL becomes the candidate protected low.
- P2 / H1 is the upside break level.
- The higher high shows that price broke above the previous high while the
  lower low remained intact.

Bullish example:

09:31 P1 / L1 = 20,000.00
09:36 P2 / H1 = 20,020.00
09:42 P3 / LL = 19,992.00
09:49 P4 / HH = 20,026.00

This is a valid bullish pattern because:

19,992.00 < 20,000.00
20,026.00 > 20,020.00

The 19,992.00 LL is the candidate protected low.


5. PROTECTED-PIVOT OUTCOME DEFINITIONS

BEARISH PROTECTED HIGH

The P3 higher high is protected if no completed 1-minute candle prints a
high
strictly greater than:

protected_high + 1 NQ tick

between structure_complete_at and 13:00 ET.

BULLISH PROTECTED LOW

The P3 lower low is protected if no completed 1-minute candle prints a low
strictly less than:

protected_low - 1 NQ tick

between structure_complete_at and 13:00 ET.

NQ tick size is 0.25 points.

OUTCOME LABELS

HELD_NO_TOUCH

The protected high or low was never touched.

HELD_EQUAL_TOUCH

The protected high or low was touched exactly, but price did not exceed it
by
one tick. This is still considered held in V1, but reported separately.

FAILED_ONE_TICK_OR_MORE

The protected high was exceeded by at least one tick, or the protected low
was
broken by at least one tick.

INSUFFICIENT_DATA

Required 1-minute data are missing between final structure confirmation and
13:00 ET.

NO_TIME_REMAINING

The structure completed too close to the 13:00 observation horizon to
receive
the predeclared observation period, if that rule is later added.


6. CANDIDATE SELECTION RULES

ONE CANDIDATE PER SEED AND NY OPEN

Use the first causally completed qualifying four-pivot structure found
between
09:30 and 10:30 ET.

Do not choose a later pattern because its result looks better.

AMBIGUOUS EXTRA PIVOTS

For V1, reject a candidate if additional confirmed pivots between P1 and P4
make
the sequence ambiguous.

Required exclusion label:

intervening_pivot_ambiguity

STRICT ORDERING

P1.pivot_ts < P2.pivot_ts < P3.pivot_ts < P4.pivot_ts

P1.pivot_available_at <= P2.pivot_available_at <= P3.pivot_available_at
<= P4.pivot_available_at

DIRECTION RELATIVE TO THE 4-HOUR SEED

Record whether the 1-minute structure agrees with or opposes the original
4-hour wick-reject direction.

Do not use this field as a filter, ranking factor, or selection rule in V1.


7. REQUIRED TABLES

TABLE 1: seed_ny_open_eligibility

One row per 4-hour seed and candidate NY open.

Required fields:

seed_id
seed_ts
seed_available_at
seed_high
seed_low
seed_width
seed_direction
range_width_atr
penetration_atr
ny_date
ny_open_ts
seed_age_hours
seed_active_at_open
eligible_after_seed
selected_first_eligible_open
included
exclusion_reason


TABLE 2: one_minute_pivot_ledger

One row per confirmed 1-minute pivot.

Required fields:

seed_id
ny_date
pivot_id
pivot_type
pivot_price
pivot_ts
pivot_available_at
bar_index_from_open
inside_open_window
left_bars
right_bars
strict_extrema


TABLE 3: structure_candidates

One row per selected four-pivot structure.

Required fields:

candidate_id
seed_id
ny_date
pattern
p1_id
p2_id
p3_id
p4_id
p1_price
p2_price
p3_price
p4_price
h1_price
l1_price
hh_price
ll_price
structure_complete_at
protected_side
protected_price
break_level
break_distance_ticks
sequence_duration_minutes
minutes_from_open_to_completion
seed_age_hours
seed_context_relation
1m_direction_vs_seed_direction
eligible_for_protection_test
exclusion_reason


TABLE 4: protection_outcomes

One row per selected candidate after 13:00 ET.

Required fields:

candidate_id
evaluation_start
observation_end
protection_held
outcome_label
equal_touch_occurred
first_equal_touch_ts
failure_ts
failure_price
failure_distance_ticks
minutes_to_failure
max_favorable_excursion_ticks
max_adverse_excursion_ticks
session_outcome
data_complete


8. SEED CONTEXT LABELS

Classify the 1-minute four-pivot pattern by its location relative to the
4-hour wick-reject range.

ABOVE_SEED_RANGE

The full pattern is above seed_high.

BELOW_SEED_RANGE

The full pattern is below seed_low.

INSIDE_SEED_RANGE

The full pattern remains within seed_low through seed_high.

CROSSES_SEED_RANGE

The pattern crosses into or out of the 4-hour seed range.

Do not filter on these labels in V1.

SEED AGE BUCKETS

0 to less than 12 hours
12 to less than 24 hours
24 to less than 48 hours
48 or more hours

DIRECTION RELATIONSHIP

ALIGN_WITH_SEED_DIRECTION
OPPOSE_SEED_DIRECTION
NOT_APPLICABLE_OR_UNCLASSIFIED


9. PRIMARY MEASUREMENTS

POPULATION

eligible_seed_count:
Number of active 4-hour wick-reject seeds with a valid assigned NY open.

candidate_rate:
Selected four-pivot candidates divided by eligible seed-opens.

bear_count:
Number of bearish H1 -> L1 -> HH -> LL formations.

bull_count:
Number of bullish L1 -> H1 -> LL -> HH formations.

FORMATION TIMING

median_completion_time:
Median clock time at which P4 becomes causally confirmed.

sequence_duration_minutes:
Time from P1 pivot timestamp through P4 causal confirmation.

PROTECTION

bear_protection_hold_rate:
Bearish candidates whose HH remains protected through 13:00 ET divided by
all
eligible bearish candidates.

bull_protection_hold_rate:
Bullish candidates whose LL remains protected through 13:00 ET divided by
all
eligible bullish candidates.

hold_rate_to_10_30
hold_rate_to_11_00
hold_rate_to_13_00

These show how long the protected level survives after formation.

median_minutes_to_failure:
Median time from final structure confirmation to the first strict break of
the
protected high or protected low.

EXCURSIONS

Report excursions in NQ ticks only.

Bearish favorable excursion:
Lowest low after structure completion through 13:00.

Bullish favorable excursion:
Highest high after structure completion through 13:00.

Maximum adverse excursion:
For bearish patterns, highest later high relative to the protected HH.
For bullish patterns, lowest later low relative to the protected LL.

Do not convert these measurements into P&L in V1.


10. MINIMUM REPORTING RULES

Minimum reporting thresholds:

- At least 80 eligible seed-opens.
- At least 40 total completed four-pivot candidates.
- At least 15 candidates per direction.

If these thresholds are not met, report the outcome as descriptive only.
Do not claim a durable structural result.

A STRUCTURE IS WORTH FURTHER RESEARCH ONLY IF:

- Bear and bull protection rates are both at least 55% through 13:00 ET.
- Both sides have enough candidates.
- Favorable excursion is meaningfully larger than adverse excursion under
the
  fixed measurement convention.
- The result is not dominated by one calendar block or a few sessions.
- All causal timestamp assertions pass.

These are research-screening criteria only. They are not permission to
trade.


11. NON-PROMOTION RULES

- A positive protection rate does not authorize a trade model.
- A high hold rate does not authorize stop placement.
- A high hold rate does not authorize targets or position sizing.
- No parameter may be changed after looking at outcomes and then called V1.
- Fewer than 40 formed candidates remains descriptive only.
- Do not combine results with S1 or S2.
- Do not build a strategy chooser.
- Do not create a plugin.
- Do not claim P&L expectancy.


12. REQUIRED CAUSALITY ASSERTIONS

Every included candidate must satisfy:

seed_available_at <= ny_open_ts

ny_open_ts <= p1.pivot_ts

p1.pivot_ts < p2.pivot_ts < p3.pivot_ts < p4.pivot_ts

p1.pivot_available_at <= p2.pivot_available_at
<= p3.pivot_available_at
<= p4.pivot_available_at

structure_complete_at = p4.pivot_available_at

structure_complete_at <= 10:30 ET

structure_complete_at < 13:00 ET

For outcome rows:

failure_ts, if present, must be at or after structure_complete_at.

No future bar may be used to identify or select P1, P2, P3, or P4 beyond the
frozen one-right-bar confirmation rule.

RECONCILIATION ASSERTIONS

- Candidate count equals outcome count plus explicit incomplete-data
exclusions.
- Every candidate maps to exactly one seed and one NY open.
- Every seed contributes at most one NY open.
- Every eligible seed-open produces at most one selected candidate.


13. ECU CHART PACK DEFINITION

PURPOSE

The ECU chart pack is an audit and verification record. It visually
documents
every eligible seed-open, candidate sequence, and protection outcome.

Charts must be generated from the immutable ledgers. A chart cannot select,
change, hide, reclassify, or exclude an event.

Every chart must show:

study_id
seed_id
candidate_id, if applicable
source data version
configuration hash
timezone
generation timestamp
outcome label

NO TRADE ANNOTATIONS

Do not draw entries, stops, targets, position size, P&L, R-multiples, or
trade
arrows on these V1 charts.


PACK A: SEED-TO-NY-OPEN CONTEXT CHART

Create one chart for every eligible 4-hour seed and assigned NY open,
including
events that never create a qualifying 1-minute pattern.

DISPLAY RANGE

- Show at least two completed 4-hour candles before the seed.
- Show the seed candle.
- Show through the 4-hour candle containing NY open.
- Include a 1-minute inset from 09:20 through 10:40 ET.
- If a candidate exists, include an outcome inset through 13:00 ET.

REQUIRED 4-HOUR ANNOTATIONS

- Highlight the 4-hour WICK_REJECT seed candle.
- Label seed_ts.
- Label seed_available_at.
- Plot seed_high horizontal line labeled SEED HIGH.
- Plot seed_low horizontal line labeled SEED LOW.
- Shade the area between seed_high and seed_low.
- Show seed width W in points and ticks.
- Show seed_direction.
- Show penetration_atr.
- Show range_width_atr.
- Show seed-expiry timestamp if visible.
- Draw a vertical NY OPEN line at 09:30 ET.
- Shade 09:30 to 10:30 ET as the formation window.
- Draw a vertical 13:00 ET protection-horizon line.
- Show seed age at NY open.
- Show whether seed was active at NY open.

REQUIRED 1-MINUTE INSET ANNOTATIONS

- 09:30 vertical line labeled NY OPEN.
- 10:30 vertical line labeled FORMATION CUT-OFF.
- 13:00 vertical line labeled PROTECTION HORIZON.
- Formation-window background shading from 09:30 to 10:30.
- Protection-window shading after completion, if a candidate exists.
- Small neutral markers for all causally confirmed 1-minute pivots.
- Large numbered markers for selected P1, P2, P3, and P4.
- Candidate pattern label, if applicable.
- Outcome label, if applicable.


PACK B: STRUCTURE FORMATION CHART

Create one chart for every selected candidate.

DISPLAY RANGE

- One-minute chart from 09:20 ET through at least 15 minutes after
  structure_complete_at.
- Include an inset or extended panel through 13:00 ET.

REQUIRED HEADER

study_id
seed_id
candidate_id
NY date
symbol
data version
frozen pivot rule: 1-left / 1-right strict 1-minute pivots
seed age at NY open
seed context relation
original 4-hour seed direction
1-minute pattern direction
alignment or opposition label

GENERAL ANNOTATIONS

- NY OPEN vertical line at 09:30 ET.
- Formation-window shading from 09:30 to 10:30 ET.
- Protection horizon line at 13:00 ET.
- All selected pivots connected in chronological order.
- Vertical line at P4.pivot_available_at labeled STRUCTURE AVAILABLE.
- Label for formation duration.
- Label for break_distance_ticks.


BEARISH FORMATION CHART ANNOTATIONS

- P1 marker: P1 H1, including timestamp and price.
- P2 marker: P2 L1, including timestamp and price.
- P3 marker: P3 HH / PROTECTED HIGH, including timestamp and price.
- P4 marker: P4 LL / STRUCTURE CONFIRMED, including timestamp and price.
- Line linking P1 -> P2 -> P3 -> P4.
- Horizontal protected-high line at P3 / HH.
- Dashed failure line at P3 / HH plus one NQ tick.
- Horizontal downside break-level line at P2 / L1.
- Bracket or label showing HH greater than H1 in ticks.
- Bracket or label showing LL less than L1 in ticks.


BULLISH FORMATION CHART ANNOTATIONS

- P1 marker: P1 L1, including timestamp and price.
- P2 marker: P2 H1, including timestamp and price.
- P3 marker: P3 LL / PROTECTED LOW, including timestamp and price.
- P4 marker: P4 HH / STRUCTURE CONFIRMED, including timestamp and price.
- Line linking P1 -> P2 -> P3 -> P4.
- Horizontal protected-low line at P3 / LL.
- Dashed failure line at P3 / LL minus one NQ tick.
- Horizontal upside break-level line at P2 / H1.
- Bracket or label showing LL less than L1 in ticks.
- Bracket or label showing HH greater than H1 in ticks.


PACK C: PROTECTION OUTCOME CHART

Create one chart for every selected candidate.

DISPLAY RANGE

From structure_complete_at through 13:00 ET using one-minute candles.

REQUIRED ANNOTATIONS

- Protected level drawn as a thick horizontal line.
- One-tick failure threshold drawn as a dashed horizontal line.
- Vertical line at structure_complete_at.
- Shaded observation area from completion through 13:00.
- Maximum favorable excursion point and distance in ticks.
- Maximum adverse excursion point and distance in ticks.
- Outcome banner at top of chart.

OUTCOME BANNERS

HELD_NO_TOUCH

Banner:
HELD TO 13:00 — NO TOUCH

Also show the closest approach to the protected level and its distance in
ticks.

HELD_EQUAL_TOUCH

Banner:
HELD TO 13:00 — EQUAL TOUCH

Mark each equal touch with EQ TOUCH.

FAILED_ONE_TICK_OR_MORE

Banner:
FAILED — PROTECTED LEVEL BROKEN

Mark the first violating 1-minute candle as FIRST FAILURE.

Show:
failure timestamp
failure price
failure distance in ticks
minutes from completion to failure

INSUFFICIENT_DATA

Banner:
INSUFFICIENT DATA — NO OUTCOME CLAIM

Shade the missing-data interval and state the exact data exception.


PACK D: NO-PATTERN AND EXCLUSION AUDIT CHART

Create one chart for every eligible seed-open that does not produce a
selected
candidate. Create charts for exclusions when data are available.

REQUIRED ANNOTATIONS

- 4-hour seed box.
- SEED HIGH and SEED LOW.
- NY OPEN line.
- Formation-window shading.
- All confirmed 1-minute pivots between 09:30 and 10:30 ET.
- Clear reason banner.

VALID REASON BANNERS

NO_COMPLETED_FOUR_PIVOT_SEQUENCE
SEQUENCE_NOT_DIRECTIONALLY_VALID
FINAL_PIVOT_AFTER_CUTOFF
INTERVENING_PIVOT_AMBIGUITY
SEED_INACTIVE
MISSING_1M_DATA
CALENDAR_EXCLUSION
OTHER_DOCUMENTED_REASON

If a near-miss sequence exists, label it:

NEAR MISS — NOT COUNTED

Show the exact failed requirement, for example:

HH was not greater than H1
LL was not lower than L1
P4 confirmation occurred after 10:30
extra pivot invalida