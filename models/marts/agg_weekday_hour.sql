-- One row per day of week x pickup hour (7 x 24 = 168 rows). Feeds the demand
-- heatmap on the executive dashboard.
--
-- day_count is the number of calendar days of that weekday in the window, so
-- trip_count / day_count is the demand of a typical Monday 08:00, and so on.
-- It comes from dim_date (not from the fact), so an hour with no trips on some
-- day still divides by the right number of days.

with day_counts as (

    select
        day_of_week_number,
        count(*) as day_count
    from {{ ref('dim_date') }}
    group by 1

),

trips as (

    select
        d.day_of_week_number,
        d.day_name,
        fct.pickup_hour,
        count(*) as trip_count,
        sum(fct.total_amount) as revenue_amount,
        sum(fct.trip_duration_minutes) as occupied_minutes
    from {{ ref('fct_trips') }} as fct
    inner join {{ ref('dim_date') }} as d
        on fct.pickup_date = d.date_day
    group by 1, 2, 3

)

select
    trips.day_of_week_number,
    trips.day_name,
    trips.pickup_hour,
    day_counts.day_count,
    trips.trip_count,
    trips.revenue_amount,
    trips.occupied_minutes,
    trips.trip_count / day_counts.day_count as avg_trips_per_day
from trips
inner join day_counts
    on trips.day_of_week_number = day_counts.day_of_week_number
