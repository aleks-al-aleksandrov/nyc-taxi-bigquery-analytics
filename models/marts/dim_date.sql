-- One row per calendar day in the configured window. Generated, not sourced.

with days as (

    select date_day
    from unnest(
        generate_date_array(
            date('{{ var("trip_start_date") }}'),
            date_sub(date('{{ var("trip_end_date") }}'), interval 1 day)
        )
    ) as date_day

)

select
    {{ to_date_key('date_day') }} as date_key,
    date_day,
    extract(year from date_day) as year_number,
    extract(quarter from date_day) as quarter_number,
    extract(month from date_day) as month_number,
    format_date('%B', date_day) as month_name,
    extract(day from date_day) as day_of_month,
    -- BigQuery DAYOFWEEK: 1 = Sunday ... 7 = Saturday
    extract(dayofweek from date_day) as day_of_week_number,
    format_date('%A', date_day) as day_name,
    extract(dayofweek from date_day) in (1, 7) as is_weekend,
    date_trunc(date_day, isoweek) as week_start_date,
    date_trunc(date_day, month) as month_start_date
from days
