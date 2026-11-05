-- One row per raw trip record in the configured date window.
-- Columns are renamed and typed. Rows are NOT dropped here: each row gets an
-- exclusion_reason (NULL = valid). fct_trips keeps only valid rows, which makes
-- the staging-vs-fact reconciliation test exact and every exclusion auditable.
--
-- NOTE: TLC timestamps are local New York wall-clock time stored in a TIMESTAMP
-- column. They are treated as naive local time; no time zone conversion is done.

with source as (

    select *
    from {{ source('nyc_taxi_public', 'tlc_yellow_trips_2022') }}
    where
        pickup_datetime >= timestamp('{{ var("trip_start_date") }}')
        and pickup_datetime < timestamp('{{ var("trip_end_date") }}')

),

renamed as (

    select
        -- The source has no natural key. The surrogate key hashes every raw
        -- column, so two rows share a trip_id only if they are exact duplicates.
        to_hex(md5(to_json_string(source))) as trip_id,

        vendor_id,
        pickup_datetime as pickup_ts,
        dropoff_datetime as dropoff_ts,
        safe_cast(pickup_location_id as int64) as pickup_zone_id,
        safe_cast(dropoff_location_id as int64) as dropoff_zone_id,
        safe_cast(payment_type as int64) as payment_type_id,
        safe_cast(rate_code as int64) as rate_code_id,
        store_and_fwd_flag,
        passenger_count,
        trip_distance as trip_distance_miles,
        fare_amount,
        extra as extra_amount,
        mta_tax as mta_tax_amount,
        tip_amount,
        tolls_amount,
        imp_surcharge as improvement_surcharge_amount,
        airport_fee as airport_fee_amount,
        total_amount,
        timestamp_diff(dropoff_datetime, pickup_datetime, second) / 60.0 as trip_duration_minutes

    from source

),

flagged as (

    select
        *,
        row_number() over (partition by trip_id order by pickup_ts) as duplicate_rank
    from renamed

)

select
    * except (duplicate_rank),
    -- Rules are evaluated in order; the first match wins. Documented in
    -- models/staging/_staging.yml and README.md.
    case
        when duplicate_rank > 1
            then 'exact_duplicate'
        when pickup_ts is null or dropoff_ts is null
            then 'missing_timestamp'
        when dropoff_ts < pickup_ts
            then 'dropoff_before_pickup'
        when trip_duration_minutes > 24 * 60
            then 'duration_over_24h'
        when
            pickup_zone_id is null or pickup_zone_id not between 1 and 265
            or dropoff_zone_id is null or dropoff_zone_id not between 1 and 265
            then 'invalid_zone'
        when trip_distance_miles is null or trip_distance_miles < 0 or trip_distance_miles > 200
            then 'implausible_distance'
        when fare_amount < 0 or total_amount < 0
            then 'negative_amount'
        when fare_amount > 1000 or total_amount > 1500
            then 'implausible_amount'
        -- Average speed above 100 mph is physically implausible in NYC traffic.
        -- Only checked for trips of at least one minute to avoid divide-by-tiny.
        when
            trip_duration_minutes >= 1
            and trip_distance_miles / (trip_duration_minutes / 60.0) > 100
            then 'implausible_speed'
    end as exclusion_reason

from flagged
