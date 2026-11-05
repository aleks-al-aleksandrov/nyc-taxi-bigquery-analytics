-- One row per TLC location id 1-265. The public zone table has 263 rows; any id
-- in 1-265 that it lacks (at least 264 Unknown and 265 Outside of NYC) is still
-- present here, so every valid trip has a matching zone row.

with all_ids as (

    select zone_id
    from unnest(generate_array(1, 265)) as zone_id

)

select
    all_ids.zone_id,
    coalesce(
        stg_zones.zone_name,
        case all_ids.zone_id
            when 264 then 'Unknown'
            when 265 then 'Outside of NYC'
            else 'Unmapped zone ' || cast(all_ids.zone_id as string)
        end
    ) as zone_name,
    coalesce(
        stg_zones.borough,
        case all_ids.zone_id
            when 265 then 'Outside of NYC'
            else 'Unknown'
        end
    ) as borough,
    stg_zones.zone_id is not null as is_in_zone_reference
from all_ids
left join {{ ref('stg_zones') }} as stg_zones
    on all_ids.zone_id = stg_zones.zone_id
