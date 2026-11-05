-- One row per TLC payment type code, from the TLC yellow trip data dictionary.
-- Built with SQL rather than a dbt seed so it needs no load job.
-- Code 0 appears in recent files for trips without a recorded payment type.

select
    payment_type_id,
    payment_type_name
from unnest([
    struct(0 as payment_type_id, 'Not recorded' as payment_type_name),
    struct(1, 'Credit card'),
    struct(2, 'Cash'),
    struct(3, 'No charge'),
    struct(4, 'Dispute'),
    struct(5, 'Unknown'),
    struct(6, 'Voided trip')
])
