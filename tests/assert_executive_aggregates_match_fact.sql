-- The two tables behind the executive dashboard must tie back to fct_trips:
-- same trip count and same revenue (to the cent), and the expected row counts
-- at their grain. A dashboard total that does not match the fact fails here.

with fact as (
    select
        count(*) as trips,
        sum(total_amount) as revenue,
        count(distinct pickup_date) as days
    from {{ ref('fct_trips') }}
),

daily as (
    select
        sum(trip_count) as trips,
        sum(revenue_amount) as revenue,
        count(*) as row_count,
        count(distinct pickup_date) as days,
        countif(
            card_trip_count + cash_trip_count > trip_count
            or airport_trip_count > trip_count
            or airport_revenue_amount > revenue_amount
        ) as inconsistent_rows
    from {{ ref('agg_daily_summary') }}
),

weekday_hour as (
    select
        sum(trip_count) as trips,
        sum(revenue_amount) as revenue,
        count(*) as row_count,
        count(distinct format('%t|%t', day_of_week_number, pickup_hour)) as cells
    from {{ ref('agg_weekday_hour') }}
)

select
    fact.trips as fact_trips,
    daily.trips as daily_trips,
    weekday_hour.trips as weekday_hour_trips,
    fact.revenue as fact_revenue,
    daily.revenue as daily_revenue,
    weekday_hour.revenue as weekday_hour_revenue,
    daily.inconsistent_rows
from fact
cross join daily
cross join weekday_hour
where
    fact.trips != daily.trips
    or fact.trips != weekday_hour.trips
    or fact.revenue != daily.revenue
    or fact.revenue != weekday_hour.revenue
    or daily.row_count != daily.days
    or daily.days != fact.days
    or weekday_hour.row_count != weekday_hour.cells
    or daily.inconsistent_rows != 0
