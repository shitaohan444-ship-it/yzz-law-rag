-- v1 占位业务 SQL，按员工+自然月统计市场人员绩效。
-- TODO: 统计区间目前固定为自然月，后续需要支持自定义区间参数化查询。
SELECT
    emp.id AS employee_id,
    emp.real_name AS employee_name,
    emp.department_id,
    DATE_TRUNC('month', call.call_start_time)::date AS stat_start_date,
    (DATE_TRUNC('month', call.call_start_time) + INTERVAL '1 month' - INTERVAL '1 day')::date AS stat_end_date,
    COUNT(DISTINCT call.id) AS call_count,
    COUNT(DISTINCT CASE WHEN call.call_connect_result = 'connected' THEN call.id END) AS connected_count,
    COUNT(DISTINCT apt.id) AS appointment_count,
    COUNT(DISTINCT CASE WHEN apt.actual_arrival_time IS NOT NULL THEN apt.id END) AS visit_count,
    COUNT(DISTINCT CASE WHEN l.lead_status = 'deal' THEN l.id END) AS deal_count,
    COALESCE(SUM(neg.deal_amount), 0::numeric) AS contract_amount,
    COALESCE(SUM(pr.received_amount), 0::numeric) AS paid_amount,
    CASE
        WHEN COUNT(DISTINCT call.id) = 0 THEN 0::numeric
        ELSE ROUND(COUNT(DISTINCT CASE WHEN l.lead_status = 'deal' THEN l.id END)::numeric * 100.0 / COUNT(DISTINCT call.id), 4)
    END AS conversion_rate
FROM oa.sys_employee emp
LEFT JOIN oa.mkt_call_record call
    ON call.caller_employee_id = emp.id
    AND call.deleted_at IS NULL
LEFT JOIN oa.crm_lead l
    ON l.owner_employee_id = emp.id
    AND l.deleted_at IS NULL
LEFT JOIN oa.mkt_appointment apt
    ON apt.lead_id = l.id
    AND apt.deleted_at IS NULL
LEFT JOIN oa.lead_negotiation_record neg
    ON neg.main_negotiator_id = emp.id
    AND neg.deleted_at IS NULL
LEFT JOIN oa.fin_payment_record pr
    ON pr.created_by = emp.id
    AND pr.deleted_at IS NULL
WHERE emp.deleted_at IS NULL
GROUP BY
    emp.id,
    emp.real_name,
    emp.department_id,
    DATE_TRUNC('month', call.call_start_time);
