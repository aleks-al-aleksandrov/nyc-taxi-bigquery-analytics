-- How many staging rows each exclusion rule removes. Paste the result into
-- README.md ("Excluded rows"). Compile with `dbt compile`, then run the
-- compiled SQL from target/compiled/ with `bq query --dry_run` first.

select
    coalesce(exclusion_reason, 'kept (valid)') as outcome,
    count(*) as row_count,
    round(100 * count(*) / sum(count(*)) over (), 3) as pct_of_staging
from {{ ref('stg_trips') }}
group by 1
order by 2 desc
