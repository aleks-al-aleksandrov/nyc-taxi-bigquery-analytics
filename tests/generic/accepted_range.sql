{#
    Fails for each row where the column is outside [min_value, max_value].
    NULLs pass (use not_null separately). Written locally instead of pulling in
    dbt_utils, so the project parses with no `dbt deps` and no network.
#}
{% test accepted_range(model, column_name, min_value=none, max_value=none) %}

select {{ column_name }}
from {{ model }}
where {{ column_name }} is not null
  and (
      false
      {% if min_value is not none %} or {{ column_name }} < {{ min_value }} {% endif %}
      {% if max_value is not none %} or {{ column_name }} > {{ max_value }} {% endif %}
  )

{% endtest %}
