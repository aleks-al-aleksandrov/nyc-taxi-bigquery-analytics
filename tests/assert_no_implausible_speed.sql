-- Anomaly check: no trip in the fact table may average more than 100 mph.
-- Staging flags these as implausible_speed; this test guards that rule against
-- regressions (e.g. someone changing the order or threshold of the rules).

select
    trip_id,
    pickup_ts,
    trip_distance_miles,
    trip_duration_minutes,
    trip_distance_miles / (trip_duration_minutes / 60.0) as avg_mph
from {{ ref('fct_trips') }}
where
    trip_duration_minutes >= 1
    and trip_distance_miles / (trip_duration_minutes / 60.0) > 100
