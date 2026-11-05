{#
    Fails for each row where the boolean SQL expression is not true.
    Example: expression: "dropoff_ts >= pickup_ts"
#}
{% test expression_is_true(model, expression) %}

select *
from {{ model }}
where not ({{ expression }})

{% endtest %}
