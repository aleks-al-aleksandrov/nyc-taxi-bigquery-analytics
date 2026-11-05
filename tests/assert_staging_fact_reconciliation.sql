-- Reconciliation: every staging row is either in fct_trips or has a documented
-- exclusion_reason. Fails (returns a row) if
--   staging rows != fact rows + excluded rows.
-- Cost: reads stg_trips (a view), so this scans the source columns once (~7 GB).
-- To see the breakdown by reason, run analyses/profiling/exclusion_breakdown.sql.

with staging as (

    select
        count(*) as staging_rows,
        countif(exclusion_reason is null) as staging_valid_rows,
        countif(exclusion_reason is not null) as staging_excluded_rows
    from {{ ref('stg_trips') }}

),

fact as (

    select count(*) as fact_rows
    from {{ ref('fct_trips') }}

)

select
    staging.staging_rows,
    staging.staging_valid_rows,
    staging.staging_excluded_rows,
    fact.fact_rows
from staging
cross join fact
where staging.staging_rows != fact.fact_rows + staging.staging_excluded_rows
