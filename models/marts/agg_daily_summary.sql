-- One row per pickup date. Feeds the executive dashboard (docs/index.html).
-- Sums are kept additive (no pre-computed ratios), so any ratio can be
-- recomputed correctly over a week, a month or the whole quarter.
--
-- "Airport trip" = pickup or dropoff in a TLC airport zone:
-- 1 Newark Airport, 132 JFK Airport, 138 LaGuardia Airport.
-- Payment type 1 = credit card, 2 = cash. Tips are only recorded for card
-- payments, so the tip rate uses card trips only.

select
    fct.pickup_date,
    d.day_name,
    d.is_weekend,
    d.month_start_date,
    count(*) as trip_count,
    sum(fct.total_amount) as revenue_amount,
    sum(fct.fare_amount) as fare_amount,
    sum(fct.tip_amount) as tip_amount,
    countif(fct.payment_type_id = 1) as card_trip_count,
    countif(fct.payment_type_id = 2) as cash_trip_count,
    sum(if(fct.payment_type_id = 1, fct.fare_amount, 0)) as card_fare_amount,
    sum(if(fct.payment_type_id = 1, fct.tip_amount, 0)) as card_tip_amount,
    countif(
        fct.pickup_zone_id in (1, 132, 138) or fct.dropoff_zone_id in (1, 132, 138)
    ) as airport_trip_count,
    sum(
        if(
            fct.pickup_zone_id in (1, 132, 138) or fct.dropoff_zone_id in (1, 132, 138),
            fct.total_amount,
            0
        )
    ) as airport_revenue_amount,
    sum(fct.trip_duration_minutes) as occupied_minutes,
    sum(fct.trip_distance_miles) as distance_miles
from {{ ref('fct_trips') }} as fct
inner join {{ ref('dim_date') }} as d
    on fct.pickup_date = d.date_day
group by 1, 2, 3, 4
