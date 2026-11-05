-- Both aggregate tables must account for exactly the trips in fct_trips, and
-- each must be unique at its declared grain.

with fact as (
    select count(*) as trips from {{ ref('fct_trips') }}
),

daily_zone as (
    select
        sum(trip_count) as trips,
        count(*) - count(distinct format('%t|%t', pickup_date, pickup_zone_id)) as duplicate_grain_rows
    from {{ ref('agg_daily_zone') }}
),

hourly as (
    select
        sum(trip_count) as trips,
        count(*) - count(distinct format('%t|%t', pickup_date, pickup_hour)) as duplicate_grain_rows
    from {{ ref('agg_hourly_demand') }}
)

select
    fact.trips as fact_trips,
    daily_zone.trips as agg_daily_zone_trips,
    hourly.trips as agg_hourly_demand_trips,
    daily_zone.duplicate_grain_rows as agg_daily_zone_duplicates,
    hourly.duplicate_grain_rows as agg_hourly_demand_duplicates
from fact
cross join daily_zone
cross join hourly
where
    fact.trips != daily_zone.trips
    or fact.trips != hourly.trips
    or daily_zone.duplicate_grain_rows != 0
    or hourly.duplicate_grain_rows != 0
