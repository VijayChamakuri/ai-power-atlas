-- Hours flagged as bad must never set a peak, or the 2% rule would rest on reporting errors.
select peaks.ba
from {{ ref('int_ba_peaks') }} as peaks
inner join {{ ref('int_demand_cleaned') }} as demand
    on peaks.ba = demand.ba and peaks.peak_mw = demand.value_mw
where not demand.is_clean
