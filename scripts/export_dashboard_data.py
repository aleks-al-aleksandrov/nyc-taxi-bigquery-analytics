"""Export the small aggregate tables behind docs/index.html to static files.

The executive dashboard is a static page (it can be opened from disk or served
by GitHub Pages), so it cannot query BigQuery itself. This script reads three
dbt aggregate tables and writes docs/dashboard_data.js. Every number on the
dashboard is computed in the browser from that file - nothing is typed by hand.

It also writes docs/zones_geo.js: the outlines of the TLC taxi zones for the
pickup map, simplified to 40 m in BigQuery and rounded to about 10 m. Shapes
only - the numbers drawn on the map still come from dashboard_data.js.

    python scripts/export_dashboard_data.py

Needs GCP_PROJECT and application-default credentials, like dbt. The queries
read under 10 MB in total; each is capped at 100 MB billed.

scripts/check_dashboard_data.py validates both files without a warehouse
connection; CI runs it on every push.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import sys
from decimal import Decimal
from pathlib import Path

from google.cloud import bigquery

DATASET = "taxi_marts"
MAX_BYTES_BILLED = 100 * 1024 * 1024
DOCS = Path(__file__).resolve().parents[1] / "docs"
OUT_PATH = DOCS / "dashboard_data.js"
GEO_PATH = DOCS / "zones_geo.js"

# Zone outlines. Coordinates are stored as integers to keep the file small:
# x = round((longitude - GEO_LON0) * GEO_SCALE), y = round((latitude - GEO_LAT0) * GEO_SCALE).
GEO_LON0 = -74.3
GEO_LAT0 = 40.4
GEO_SCALE = 10000
GEO_TOLERANCE_M = 40
GEO_QUERY = """
    select
        safe_cast(zone_id as int64) as zone_id,
        st_asgeojson(st_simplify(zone_geom, {tolerance})) as geojson
    from `bigquery-public-data.new_york_taxi_trips.taxi_zone_geom`
    where safe_cast(zone_id as int64) is not null
    order by 1
"""

QUERIES = {
    # [date, trips, revenue, tips, card_trips, cash_trips, card_fare, card_tips,
    #  airport_trips, airport_revenue, occupied_minutes, miles]
    "daily": """
        select
            format_date('%Y-%m-%d', pickup_date), trip_count, revenue_amount, tip_amount,
            card_trip_count, cash_trip_count, card_fare_amount, card_tip_amount,
            airport_trip_count, airport_revenue_amount, occupied_minutes, distance_miles
        from `{project}.{dataset}.agg_daily_summary`
        order by 1
    """,
    # [day_of_week (1 = Sunday), hour, day_count, trips, revenue, occupied_minutes]
    "weekday_hour": """
        select day_of_week_number, pickup_hour, day_count, trip_count, revenue_amount, occupied_minutes
        from `{project}.{dataset}.agg_weekday_hour`
        order by 1, 2
    """,
    # [zone_id, zone_name, borough, trips, revenue]
    "zones": """
        select
            pickup_zone_id, any_value(pickup_zone_name), any_value(pickup_borough),
            sum(trip_count), sum(revenue_amount)
        from `{project}.{dataset}.agg_daily_zone`
        group by 1
        order by 4 desc
    """,
}


def plain(value):
    """BigQuery NUMERIC arrives as Decimal; keep cents, drop the type."""
    if isinstance(value, Decimal):
        return round(float(value), 2)
    if isinstance(value, float):
        return round(value, 2)
    return value


def polygons_of(geom: dict) -> list:
    """Polygon coordinate lists inside any GeoJSON geometry.

    ST_SIMPLIFY returns a GeometryCollection when thin parts of a zone collapse
    into lines; those lines and points are dropped, the polygons are kept.
    """
    if geom["type"] == "Polygon":
        return [geom["coordinates"]]
    if geom["type"] == "MultiPolygon":
        return list(geom["coordinates"])
    if geom["type"] == "GeometryCollection":
        return [p for member in geom["geometries"] for p in polygons_of(member)]
    return []


def rings(geojson: str) -> list[list[int]]:
    """Outer rings of a zone as flat [x, y, x, y, ...] integer lists."""
    polygons = polygons_of(json.loads(geojson))
    out = []
    for polygon in polygons:
        flat: list[int] = []
        for lon, lat in polygon[0]:  # index 0 = outer ring; holes are not drawn
            x = round((lon - GEO_LON0) * GEO_SCALE)
            y = round((lat - GEO_LAT0) * GEO_SCALE)
            if flat[-2:] != [x, y]:
                flat += [x, y]
        if len(flat) >= 8:  # at least three distinct points plus the closing one
            out.append(flat)
    return out


def export_geo(client: bigquery.Client, config: bigquery.QueryJobConfig) -> None:
    job = client.query(GEO_QUERY.format(tolerance=GEO_TOLERANCE_M), job_config=config)
    zones: dict[int, list[list[int]]] = {}
    for row in job.result():
        # the public table repeats a few zone ids (one row per island), so merge them
        zones.setdefault(row["zone_id"], []).extend(rings(row["geojson"]))
    geo = {
        "lon0": GEO_LON0,
        "lat0": GEO_LAT0,
        "scale": GEO_SCALE,
        "zones": [[zone_id, shapes] for zone_id, shapes in sorted(zones.items()) if shapes],
    }
    print(f"geo: {len(geo['zones'])} zones, {job.total_bytes_processed:,} bytes processed")
    GEO_PATH.write_text(
        "// Generated by scripts/export_dashboard_data.py - do not edit by hand.\n"
        f"window.ZONES_GEO = {json.dumps(geo, separators=(',', ':'))};\n",
        encoding="utf-8",
    )
    print(f"wrote {GEO_PATH} ({GEO_PATH.stat().st_size:,} bytes)")


def main() -> int:
    project = os.environ.get("GCP_PROJECT")
    if not project:
        print("Set GCP_PROJECT first.", file=sys.stderr)
        return 1

    client = bigquery.Client(project=project, location="US")
    config = bigquery.QueryJobConfig(maximum_bytes_billed=MAX_BYTES_BILLED)

    data = {"generated_on": dt.date.today().isoformat()}
    for name, sql in QUERIES.items():
        job = client.query(sql.format(project=project, dataset=DATASET), job_config=config)
        data[name] = [[plain(v) for v in row.values()] for row in job.result()]
        print(f"{name}: {len(data[name])} rows, {job.total_bytes_processed:,} bytes processed")

    OUT_PATH.write_text(
        "// Generated by scripts/export_dashboard_data.py - do not edit by hand.\n"
        f"window.DASHBOARD_DATA = {json.dumps(data, separators=(',', ':'))};\n",
        encoding="utf-8",
    )
    print(f"wrote {OUT_PATH} ({OUT_PATH.stat().st_size:,} bytes)")
    export_geo(client, config)
    return 0


if __name__ == "__main__":
    sys.exit(main())
