"""Check the two generated files the executive dashboard is published from.

dbt tests cover the tables in BigQuery. This covers the last step: the files
in docs/ that are committed and served by GitHub Pages. It needs no warehouse
connection and no credentials, so CI runs it on every push.

    python scripts/check_dashboard_data.py

Exit code 0 when every check passes, 1 otherwise. Standard library only.
"""

from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

DOCS = Path(__file__).resolve().parents[1] / "docs"
MAX_UNMAPPED_PICKUP_SHARE = 0.02  # zones 264 Unknown and 265 Outside of NYC have no outline


def load(name: str, variable: str) -> dict:
    """Read `window.<variable> = {...};` from a generated .js file."""
    text = (DOCS / name).read_text(encoding="utf-8")
    prefix = f"window.{variable} = "
    start = text.index(prefix) + len(prefix)
    return json.loads(text[start : text.rindex(";")])


def main() -> int:
    failures: list[str] = []

    def check(ok: bool, message: str) -> None:
        if not ok:
            failures.append(message)

    data = load("dashboard_data.js", "DASHBOARD_DATA")
    geo = load("zones_geo.js", "ZONES_GEO")
    daily, weekday_hour, zones = data["daily"], data["weekday_hour"], data["zones"]

    # daily: one row per date, no gaps, internally consistent
    dates = [dt.date.fromisoformat(row[0]) for row in daily]
    check(all(len(row) == 12 for row in daily), "daily: every row must have 12 values")
    check(
        all(b - a == dt.timedelta(days=1) for a, b in zip(dates, dates[1:])),
        "daily: dates must be consecutive with no gaps or duplicates",
    )
    for row in daily:
        date, trips, revenue = row[0], row[1], row[2]
        check(trips > 0 and revenue > 0, f"daily {date}: trips and revenue must be positive")
        check(row[4] + row[5] <= trips, f"daily {date}: card + cash trips exceed trips")
        check(row[8] <= trips and row[9] <= revenue, f"daily {date}: airport exceeds total")
        check(row[7] <= row[6], f"daily {date}: card tips exceed card fares")

    # weekday_hour: 7 x 24 cells, and the day counts add up to the number of dates
    cells = {(row[0], row[1]) for row in weekday_hour}
    expected = {(dow, hour) for dow in range(1, 8) for hour in range(24)}
    check(len(weekday_hour) == 168 and cells == expected, "weekday_hour: must be exactly 7 x 24 cells")
    day_counts: dict[int, set[int]] = {}
    for row in weekday_hour:
        day_counts.setdefault(row[0], set()).add(row[2])
    check(all(len(v) == 1 for v in day_counts.values()), "weekday_hour: day_count differs within a weekday")
    check(
        sum(min(v) for v in day_counts.values()) == len(daily),
        "weekday_hour: day counts do not add up to the number of daily rows",
    )

    # the three tables must describe the same trips and the same revenue
    trips = {
        "daily": sum(row[1] for row in daily),
        "weekday_hour": sum(row[3] for row in weekday_hour),
        "zones": sum(row[3] for row in zones),
    }
    revenue = {
        "daily": sum(row[2] for row in daily),
        "weekday_hour": sum(row[4] for row in weekday_hour),
        "zones": sum(row[4] for row in zones),
    }
    check(len(set(trips.values())) == 1, f"trip totals differ between tables: {trips}")
    check(
        max(revenue.values()) - min(revenue.values()) < 1.0,
        f"revenue totals differ by a dollar or more: {revenue}",
    )
    zone_ids = [row[0] for row in zones]
    check(len(zone_ids) == len(set(zone_ids)), "zones: duplicate zone id")

    # map outlines: well-formed, unique, and covering nearly all pickups
    geo_ids = [zone[0] for zone in geo["zones"]]
    check(len(geo_ids) == len(set(geo_ids)), "geo: duplicate zone id")
    for zone_id, shapes in geo["zones"]:
        check(len(shapes) > 0, f"geo zone {zone_id}: no outline")
        for ring in shapes:
            check(len(ring) >= 8 and len(ring) % 2 == 0, f"geo zone {zone_id}: malformed ring")
            check(ring[:2] == ring[-2:], f"geo zone {zone_id}: ring is not closed")
    mapped = set(geo_ids)
    unmapped = sum(row[3] for row in zones if row[0] not in mapped)
    check(
        unmapped / trips["zones"] <= MAX_UNMAPPED_PICKUP_SHARE,
        f"geo: {unmapped:,} pickups are in zones with no outline (limit {MAX_UNMAPPED_PICKUP_SHARE:.0%})",
    )

    # the page must load both files
    page = (DOCS / "index.html").read_text(encoding="utf-8")
    for name in ("dashboard_data.js", "zones_geo.js"):
        check(f'src="{name}"' in page, f"index.html does not load {name}")

    if failures:
        print(f"{len(failures)} check(s) failed:")
        for message in failures:
            print(f"  - {message}")
        return 1
    print(
        f"dashboard data OK: {len(daily)} days, {trips['daily']:,} trips, "
        f"${revenue['daily']:,.2f} revenue, {len(zones)} pickup zones, {len(geo_ids)} outlines"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
