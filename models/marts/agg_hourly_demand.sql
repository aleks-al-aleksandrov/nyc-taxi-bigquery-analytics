-- One row per pickup date x pickup hour (0-23). Feeds the Looker Studio report.

select
    fct.pickup_date,
    fct.pickup_hour,
    d.day_name,
    d.is_weekend,
    count(*) as trip_count,
    sum(fct.total_amount) as revenue_amount,
    avg(fct.trip_duration_minutes) as avg_duration_minutes,
    avg(fct.trip_distance_miles) as avg_distance_miles,
    avg(fct.passenger_count) as avg_passenger_count
from {{ ref('fct_trips') }} as fct
inner join {{ ref('dim_date') }} as d
    on fct.pickup_date = d.date_day
group by 1, 2, 3, 4
