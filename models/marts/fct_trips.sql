-- One row per valid trip. Integer-range partitioned on pickup_date_key (YYYYMMDD,
-- one partition per day; see macros/date_key_partition.sql for why not DATE
-- partitioning) and clustered by pickup zone and payment type, matching the
-- most common filters (a date range plus a zone and/or payment type). This is the "partitioned + clustered" variant of
-- the performance study; the other two variants live in models/perf/.

{{
    config(
        partition_by=date_key_partition(),
        cluster_by=["pickup_zone_id", "payment_type_id"]
    )
}}

select
    trip_id,
    {{ to_date_key('date(pickup_ts)') }} as pickup_date_key,
    date(pickup_ts) as pickup_date,
    extract(hour from pickup_ts) as pickup_hour,
    pickup_ts,
    dropoff_ts,
    pickup_zone_id,
    dropoff_zone_id,
    payment_type_id,
    vendor_id,
    rate_code_id,
    store_and_fwd_flag,
    passenger_count,
    trip_distance_miles,
    trip_duration_minutes,
    fare_amount,
    extra_amount,
    mta_tax_amount,
    tip_amount,
    tolls_amount,
    improvement_surcharge_amount,
    airport_fee_amount,
    total_amount
from {{ ref('stg_trips') }}
where exclusion_reason is null
