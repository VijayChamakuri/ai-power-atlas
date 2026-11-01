{% test has_rows(model) %}
    select 1 as empty_table
    where not exists (select 1 from {{ model }})
{% endtest %}
