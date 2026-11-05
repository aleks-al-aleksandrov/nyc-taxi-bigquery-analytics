# Performance study: partitioning, clustering and query shape on BigQuery

Every number below was measured on 2026-11-05 by
[`scripts/run_perf_study.py`](../scripts/run_perf_study.py). Raw per-run data
is in [`perf_results.csv`](perf_results.csv) and the generated table is in
[`perf_results.md`](perf_results.md).

## Question

For the same data and the same SQL, how much do partitioning and clustering
change **bytes processed**, **bytes billed** and **runtime** in BigQuery? And how
much do two query-shape habits matter: `SELECT *` vs. named columns, and
`COUNT(DISTINCT)` vs. `APPROX_COUNT_DISTINCT`?

## Setup

| Item | Value |
|---|---|
| Data | NYC TLC yellow taxi trips, pickups 2022-01-01 to 2022-03-31, after the exclusion rules in `stg_trips`: **9,016,981 rows**, 90 days |
| Environment | BigQuery sandbox (no billing account), project `fta-portfolio`, location US, on-demand pricing model |
| Table variants | `fct_trips_unpartitioned` · `fct_trips_partitioned` (integer range on `pickup_date_key`, one partition per day) · `fct_trips` (same partitioning, clustered on `pickup_zone_id, payment_type_id`) |
| Same data? | Yes. Both perf variants are `select * from fct_trips`; all 9,016,981 rows in each. |
| Runs | One dry run, then 3 real runs per query and table, `use_query_cache=False`. Bytes are from the first real run (they were identical across runs); runtime and slot time are medians. |

### Why integer-range partitioning, not DATE partitioning

The first build used ordinary day partitioning on `pickup_date` and produced
a fact table with **0 rows**. All the column tests passed anyway, because
they had nothing to check. Only the reconciliation test failed (9,071,205
staging rows ≠ 0 fact rows + 54,224 excluded).

The cause: the sandbox applies a **60-day partition expiration**
(`timePartitioning.expirationMs = 5184000000`) to time-partitioned tables.
Every 2022 partition was already older than 60 days, so BigQuery dropped it
on write. Integer-range partitions have no time-based expiration, so
`fct_trips` is partitioned on `pickup_date_key` (YYYYMMDD, `INT64`) instead.
See [`macros/date_key_partition.sql`](../macros/date_key_partition.sql).

The cost of this choice is that pruning only happens when a query filters on
`pickup_date_key`. Query q2b below measures what happens when it doesn't.

### Reproduce

```bash
dbt build --profiles-dir .
dbt build --profiles-dir . --select tag:perf --vars '{build_perf: true}'
python scripts/run_perf_study.py --project $GCP_PROJECT --dry-run-only
python scripts/run_perf_study.py --project $GCP_PROJECT
```

Total cost of one full study run: ~9.4 GB processed (estimated by the dry run).

## Experiment 1: table design

| Query | Filter | Unpartitioned billed | Partitioned billed | Partitioned + clustered billed | Clustered: dry-run estimate vs. actual processed |
|---|---|---:|---:|---:|---|
| q1 one month, one zone | `pickup_date_key` (28 days) + zone 161 | 276 MB | 91 MB (−67%) | **83 MB (−70%)** | 90.4 MB est. → 82.6 MB |
| q2 one day, all zones | `pickup_date_key` (1 day) | 276 MB | 10 MB (−96%) | 10 MB (−96%) | 3.4 MB → 3.4 MB |
| q2b one day, filter on DATE column | `pickup_date` (1 day) | 276 MB | **276 MB (0%)** | **10 MB (−96%)** | 275.2 MB est. → 3.4 MB |
| q3 all dates, one zone | zone 161 only | 138 MB | 138 MB (0%) | 127 MB (−8%) | 137.6 MB est. → 126.1 MB |
| q4 one month, payment type only | `pickup_date_key` (28 days) + cash | 276 MB | 91 MB (−67%) | 91 MB (−67%) | 90.4 MB → 90.4 MB |
| q5 full table (control) | none | 207 MB | 207 MB | 207 MB | 206.4 MB → 206.4 MB |

Results agreed across designs (q1: 114,001 trips; q4: 552,887; q2, q2b: 217 zone rows), so each design returned the same answer.

Median runtime was 180–400 ms for every query on every design. Slot time
ranged from 15 ms (q2, pruned) to 1,400 ms (q5, clustered). Full numbers are in
[`perf_results.md`](perf_results.md).

### What each result means

**q1, partitioning plus the first cluster column (as expected).**
Partitioning cut bytes billed by two thirds, because 28 of 90 days were read.
Clustering on zone took off another ~9%. The dry run estimated 90.4 MB for the
clustered table but the query actually processed 82.6 MB. This confirms the
expectation that **dry-run estimates for clustered tables are an upper bound**:
BigQuery prunes clustered blocks only while the query runs.

**q2, the 10 MB minimum (as expected).** One day is 3.4 MB of the needed
columns, but bytes billed show **10 MB**. On-demand pricing bills at least
10 MB per table referenced, so for very selective queries on small tables the
minimum, not the data, sets the cost.

**q2b, filter on the wrong column (unexpected).** On the partitioned-only
table, filtering on `pickup_date` instead of `pickup_date_key` scanned the whole
table (276 MB). The partitioning saved nothing, which was expected. The surprise
is the clustered table: the dry run also estimated a full scan (275.2 MB), but
the real query processed only 3.4 MB, the same as filtering on the partition
column. The most likely explanation is that BigQuery keeps block-level metadata
(such as min/max values) for clustered tables and skips blocks at run time
using predicates on non-clustered columns too. Here every partition holds
exactly one date, so every block outside the target day can be skipped. I have
not confirmed this in the documentation. **Lesson:** the dry run said 275 MB and
the real query cost 10 MB, so on clustered tables the dry-run number is
reliable only as a ceiling.

**q3, clustering only (smaller than expected, consistent with hypothesis 3).**
Filtering on one zone with no date filter cut bytes by only 8%. The table is
small: each day partition holds about 100k rows, a few MB per column. Clustering
sorts rows within each partition into storage blocks. With so little data per
partition there are few blocks, and most blocks span several zones, so few can
be skipped. The benefit should grow with partition size; this study did not
measure that.

**q4, the second cluster column alone (as expected).** Filtering on
`payment_type_id` gave **no** clustering benefit (91 MB vs. 91 MB). Rows are
sorted by zone first and payment type second, so cash trips are spread across
every block. Cluster column order matters: only the first column (or a prefix
of the columns) is useful on its own.

**q5, control (as expected).** No filter, identical bytes on every design.
Partitioning and clustering do not make a full scan more expensive in bytes.
Slot time varied (661–1,400 ms) with no consistent pattern, which is normal
run-to-run noise in the shared sandbox.

**Runtime.** At this table size every query finished in well under half a
second and runtime differences were within noise. **Bytes billed is the metric
that changed, and it is the one that sets cost** under on-demand pricing.

## Experiment 2: query shape (on `fct_trips`)

| Comparison | A | B | Difference |
|---|---|---|---|
| `SELECT *` vs. 3 named columns, one day, `LIMIT 100` | `SELECT *`: 27.6 MB processed, 28 MB billed | 3 columns: 4.2 MB processed, **10 MB billed** (minimum) | −85% processed, −64% billed |
| `COUNT(DISTINCT pickup_ts)` vs. `APPROX_COUNT_DISTINCT` | exact: 69 MB billed, 4,179 slot ms, 664 ms | approx: 69 MB billed, **2,403 slot ms, 405 ms** | bytes identical; −43% slot time, −39% runtime |

**`SELECT *`.** BigQuery stores data by column and bills for the columns a query
reads. `LIMIT 100` did not reduce bytes: both queries read the whole day
partition for the columns they named. Selecting 3 of 23 columns processed
85% fewer bytes. The 10 MB minimum hid part of that saving in the bill.

**Approximate distinct count.** Both versions read the same single column, so
the cost was identical. The approximate version used 43% less slot time. Its
answer was 4,673,802 against an exact 4,676,793, a relative error of
**−0.064%**. Under on-demand pricing this is a speed optimization, not a
cost optimization. It would affect cost only under capacity (slot-based)
pricing.

## Summary

| Finding | Evidence |
|---|---|
| Partition pruning is the biggest lever when queries filter on the partition column | q1 −67%, q2 −96% |
| ...and does nothing when they don't | q2b on the partitioned table: 0% |
| Clustering added a small extra saving at this table size | q1 −9% vs. partitioned, q3 −8% |
| Only the first cluster column helps on its own | q4: 0% |
| Dry runs overestimate clustered tables | q1, q3, and q2b (275 MB estimate → 3.4 MB) |
| Small queries hit the 10 MB billing minimum | q2, e2b |
| Column selection matters, `LIMIT` does not | e2a vs. e2b: −85% processed |
| `APPROX_COUNT_DISTINCT` saves time, not bytes | e2c vs. e2d: same bytes, −43% slot ms, −0.064% error |
| Sandbox time partitions expire after 60 days | First build: 0 rows; fixed with integer-range partitioning |

## Caveats

- 9M rows over 90 days is small for BigQuery. Clustering benefits generally grow with table and partition size; this study does not show how much.
- Runtime and slot time in the shared free sandbox vary between runs. Bytes were deterministic across all three runs; time is a median of three.
- The q2b explanation is my best reading of the evidence, not something confirmed in the documentation.
- Sandbox only: on-demand model, no reservations, so slot behaviour may differ from a paid project.
