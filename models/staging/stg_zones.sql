-- One row per TLC taxi zone. Geometry is dropped (not needed downstream, and it
-- is most of the table's bytes). Deduplicated defensively on zone_id.

with source as (

    select
        safe_cast(zone_id as int64) as zone_id,
        zone_name,
        borough
    from {{ source('nyc_taxi_public', 'taxi_zone_geom') }}

)

select *
from source
where zone_id is not null
qualify row_number() over (partition by zone_id order by zone_name) = 1
