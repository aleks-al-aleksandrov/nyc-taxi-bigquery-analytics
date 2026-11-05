-- One row per pickup date x pickup zone. Feeds the Looker Studio report.

select
    fct.pickup_date,
    fct.pickup_zone_id,
    zones.zone_name as pickup_zone_name,
    zones.borough as pickup_borough,
    count(*) as trip_count,
    sum(fct.total_amount) as revenue_amount,
    sum(fct.fare_amount) as fare_amount,
    avg(fct.tip_amount) as avg_tip_amount,
    -- Tips are only recorded for card payments, so a card-only tip rate is more meaningful.
    safe_divide(
        sum(if(fct.payment_type_id = 1, fct.tip_amount, 0)),
        sum(if(fct.payment_type_id = 1, fct.fare_amount, 0))
    ) as card_tip_rate,
    avg(fct.trip_duration_minutes) as avg_duration_minutes,
    avg(fct.trip_distance_miles) as avg_distance_miles
from {{ ref('fct_trips') }} as fct
inner join {{ ref('dim_zone') }} as zones
    on fct.pickup_zone_id = zones.zone_id
group by 1, 2, 3, 4
