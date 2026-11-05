"""Performance study runner for docs/performance.md.

Runs a fixed set of queries against the three fct_trips variants (and a second
set of query-shape experiments against fct_trips), first as a dry run, then for
real with the query cache disabled. Records bytes processed, bytes billed, slot
milliseconds and wall-clock runtime for every run, and writes:

    docs/perf_results.csv   one row per (query, table, repeat)
    docs/perf_results.md    median per (query, table), ready to paste

Every number in docs/performance.md must come from these files.

Prerequisites:
    gcloud auth application-default login
    dbt build --profiles-dir .                       # builds fct_trips
    dbt build --profiles-dir . --select tag:perf --vars '{build_perf: true}'     # builds the two other variants

Usage:
    python scripts/run_perf_study.py --project YOUR_PROJECT [--repeats 3] [--dry-run-only]
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import os
import statistics
import sys
from pathlib import Path

from google.cloud import bigquery

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"

# Hard per-query cap, same idea as maximum_bytes_billed in profiles.yml.
MAX_BYTES_BILLED = 5 * 1024**3

# Zone 161 = Midtown Center (one of the busiest pickup zones).
ZONE = 161
# Partition pruning needs a filter on the integer partition column pickup_date_key
# (YYYYMMDD). See macros/date_key_partition.sql for why it is not a DATE column.
MONTH_START_KEY = 20220201
MONTH_END_KEY = 20220228  # inclusive
ONE_DAY_KEY = 20220215
ONE_DAY = "2022-02-15"

VARIANTS = {
    "unpartitioned": "fct_trips_unpartitioned",
    "partitioned": "fct_trips_partitioned",
    "partitioned_clustered": "fct_trips",
}

# Experiment 1: identical SQL against each variant. {t} is the table.
EXPERIMENT_1 = {
    "q1_one_month_one_zone": f"""
        select count(*) as trips, sum(total_amount) as revenue
        from {{t}}
        where pickup_date_key between {MONTH_START_KEY} and {MONTH_END_KEY}
          and pickup_zone_id = {ZONE}""",
    "q2_one_day_all_zones": f"""
        select pickup_zone_id, count(*) as trips, avg(tip_amount) as avg_tip
        from {{t}}
        where pickup_date_key = {ONE_DAY_KEY}
        group by pickup_zone_id""",
    # Same as q2 but filtered on the DATE column, not the partition column:
    # shows that integer-range partitioning only prunes on its own column.
    "q2b_one_day_filter_on_date_column": f"""
        select pickup_zone_id, count(*) as trips, avg(tip_amount) as avg_tip
        from {{t}}
        where pickup_date = '{ONE_DAY}'
        group by pickup_zone_id""",
    "q3_all_dates_one_zone": f"""
        select pickup_date, count(*) as trips
        from {{t}}
        where pickup_zone_id = {ZONE}
        group by pickup_date""",
    "q4_one_month_payment_type_only": f"""
        select count(*) as trips, avg(tip_amount) as avg_tip
        from {{t}}
        where pickup_date_key between {MONTH_START_KEY} and {MONTH_END_KEY}
          and payment_type_id = 2""",
    "q5_full_table_control": """
        select date_trunc(pickup_date, month) as month, count(*) as trips,
               sum(total_amount) as revenue
        from {t}
        group by month""",
}

# Experiment 2: query-shape comparisons on fct_trips only.
EXPERIMENT_2 = {
    "e2a_select_star_one_day": f"""
        select *
        from {{t}}
        where pickup_date_key = {ONE_DAY_KEY}
        limit 100""",
    "e2b_select_columns_one_day": f"""
        select pickup_ts, pickup_zone_id, total_amount
        from {{t}}
        where pickup_date_key = {ONE_DAY_KEY}
        limit 100""",
    "e2c_count_distinct_exact": """
        select count(distinct pickup_ts) as distinct_pickup_ts
        from {t}""",
    "e2d_count_distinct_approx": """
        select approx_count_distinct(pickup_ts) as distinct_pickup_ts
        from {t}""",
}


def run(client: bigquery.Client, sql: str, dry_run: bool) -> dict:
    cfg = bigquery.QueryJobConfig(
        dry_run=dry_run,
        use_query_cache=False,
        maximum_bytes_billed=MAX_BYTES_BILLED,
        labels={"study": "perf"},
    )
    job = client.query(sql, job_config=cfg)
    if dry_run:
        return {"bytes_processed": job.total_bytes_processed}
    rows = list(job.result())
    first_value = None
    if len(rows) == 1 and len(rows[0]) >= 1:
        first_value = rows[0][0]
    return {
        "job_id": job.job_id,
        "bytes_processed": job.total_bytes_processed,
        "bytes_billed": job.total_bytes_billed,
        "slot_ms": job.slot_millis,
        "elapsed_ms": int((job.ended - job.started).total_seconds() * 1000),
        "cache_hit": job.cache_hit,
        "result_rows": len(rows),
        "first_value": first_value,
    }


def human_bytes(n: int | None) -> str:
    if n is None:
        return "-"
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:,.1f} {unit}" if unit != "B" else f"{n} B"
        n /= 1024
    return str(n)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", default=os.environ.get("GCP_PROJECT"))
    parser.add_argument("--dataset", default="taxi_marts")
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--dry-run-only", action="store_true")
    args = parser.parse_args()
    if not args.project:
        parser.error("--project or GCP_PROJECT is required")

    client = bigquery.Client(project=args.project, location="US")

    plan = []
    for qname, sql in EXPERIMENT_1.items():
        for variant, table in VARIANTS.items():
            plan.append((qname, variant, sql.format(t=f"`{args.project}.{args.dataset}.{table}`")))
    for qname, sql in EXPERIMENT_2.items():
        plan.append((qname, "partitioned_clustered", sql.format(t=f"`{args.project}.{args.dataset}.fct_trips`")))

    # Dry runs first: validates every query and shows the estimate before spending quota.
    dry = {}
    total_estimate = 0
    for qname, variant, sql in plan:
        est = run(client, sql, dry_run=True)["bytes_processed"]
        dry[(qname, variant)] = est
        total_estimate += est * args.repeats
        print(f"dry-run  {qname:34s} {variant:22s} {human_bytes(est):>12s}")
    print(f"Estimated total processed for real runs: {human_bytes(total_estimate)}")
    if args.dry_run_only:
        return 0

    started = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    records = []
    for qname, variant, sql in plan:
        for i in range(1, args.repeats + 1):
            r = run(client, sql, dry_run=False)
            r.update(query=qname, variant=variant, repeat=i, dry_run_bytes=dry[(qname, variant)])
            records.append(r)
            print(
                f"run {i}    {qname:34s} {variant:22s} "
                f"billed={human_bytes(r['bytes_billed']):>10s} elapsed={r['elapsed_ms']} ms"
            )

    DOCS.mkdir(exist_ok=True)
    fields = ["query", "variant", "repeat", "dry_run_bytes", "bytes_processed", "bytes_billed",
              "slot_ms", "elapsed_ms", "cache_hit", "result_rows", "first_value", "job_id"]
    with open(DOCS / "perf_results.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(records)

    lines = [
        f"<!-- Generated by scripts/run_perf_study.py at {started}; "
        f"project dataset {args.dataset}; {args.repeats} runs each, cache disabled. -->",
        "",
        "| Query | Table design | Dry-run estimate | Bytes processed | Bytes billed | Median runtime (ms) | Median slot ms | Result |",
        "|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for qname, variant, _ in plan:
        rs = [r for r in records if r["query"] == qname and r["variant"] == variant]
        first = rs[0]
        result = first["first_value"] if first["first_value"] is not None else f"{first['result_rows']} rows"
        lines.append(
            f"| {qname} | {variant} | {human_bytes(first['dry_run_bytes'])} "
            f"| {human_bytes(first['bytes_processed'])} | {human_bytes(first['bytes_billed'])} "
            f"| {statistics.median(r['elapsed_ms'] for r in rs):,.0f} "
            f"| {statistics.median(r['slot_ms'] or 0 for r in rs):,.0f} "
            f"| {result} |"
        )
    (DOCS / "perf_results.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {DOCS / 'perf_results.csv'} and {DOCS / 'perf_results.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
