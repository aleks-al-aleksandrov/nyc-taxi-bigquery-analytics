-- Performance study variant 1: same rows and columns as fct_trips, but neither
-- partitioned nor clustered. Built from fct_trips so all three variants hold
-- identical data. Build with: dbt build --select tag:perf --vars '{build_perf: true}'

{{ config(materialized='table') }}

select * from {{ ref('fct_trips') }}
