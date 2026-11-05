{#
    Partition spec for fact tables: integer-range partitioning on pickup_date_key
    (YYYYMMDD), one partition per key value.

    Why not day partitioning on pickup_date? The BigQuery sandbox forces a
    60-day partition expiration on time-unit partitioned tables. Every 2022
    partition is older than 60 days, so it expired as soon as it was written and
    the table ended up with 0 rows (found by assert_staging_fact_reconciliation).
    Integer-range partitions have no time-based expiration.

    Trade-off: queries must filter on pickup_date_key to prune partitions;
    a filter on pickup_date alone scans every partition.
#}
{% macro date_key_partition() %}
    {%- set start_key = var("trip_start_date") | replace("-", "") | int -%}
    {%- set end_key = var("trip_end_date") | replace("-", "") | int -%}
    {{ return({
        "field": "pickup_date_key",
        "data_type": "int64",
        "range": {"start": start_key, "end": end_key + 1, "interval": 1}
    }) }}
{% endmacro %}

{% macro to_date_key(date_expr) -%}
    cast(format_date('%Y%m%d', {{ date_expr }}) as int64)
{%- endmacro %}
