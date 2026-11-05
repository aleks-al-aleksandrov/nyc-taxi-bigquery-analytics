-- Performance study variant 2: integer-range partitioned on pickup_date_key
-- (one partition per day, same spec as fct_trips), not clustered.
-- Variant 3 (partitioned + clustered) is fct_trips itself.

{{
    config(
        materialized='table',
        partition_by=date_key_partition()
    )
}}

select * from {{ ref('fct_trips') }}
