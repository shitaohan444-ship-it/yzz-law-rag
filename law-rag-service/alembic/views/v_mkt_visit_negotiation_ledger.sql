-- v1 占位业务 SQL，按预约+谈案记录还原谈案上门情况台账。
-- TODO: visit_time 需要按实际业务规则从 appointment_time 或 actual_arrival_time 提取；balance_detail 需要从回款计划拼接。
SELECT
    apt.id AS appointment_id,
    neg.id AS negotiation_id,
    COALESCE(apt.actual_arrival_time::date, apt.appointment_time::date) AS visit_date,
    TO_CHAR(COALESCE(apt.actual_arrival_time, apt.appointment_time), 'HH24:MI') AS visit_time,
    l.lead_no,
    pm.mobile AS party_phone,
    COALESCE(dt_type.item_label, l.case_type::text) AS case_type,
    main_emp.real_name AS main_negotiator_name,
    assist_emp.real_name AS assistant_negotiator_name,
    COALESCE(neg.key_case_flag, l.key_case_flag) AS key_case_flag,
    COALESCE(neg.deal_amount, l.deal_amount, 0::numeric) AS deal_amount,
    COALESCE(neg.received_amount, l.received_amount, 0::numeric) AS received_amount,
    COALESCE(neg.payment_terms_snapshot, '') AS balance_detail,
    COALESCE(neg.customer_objection, l.case_brief, '') AS case_detail,
    neg.remark
FROM oa.mkt_appointment apt
INNER JOIN oa.crm_lead l
    ON l.id = apt.lead_id
    AND l.deleted_at IS NULL
LEFT JOIN oa.lead_negotiation_record neg
    ON neg.appointment_id = apt.id
    AND neg.deleted_at IS NULL
LEFT JOIN oa.party_main pm
    ON pm.id = l.primary_party_id
    AND pm.deleted_at IS NULL
LEFT JOIN oa.sys_employee main_emp
    ON main_emp.id = COALESCE(neg.main_negotiator_id, l.main_negotiator_id)
    AND main_emp.deleted_at IS NULL
LEFT JOIN oa.sys_employee assist_emp
    ON assist_emp.id = COALESCE(neg.assistant_negotiator_id, l.assistant_negotiator_id)
    AND assist_emp.deleted_at IS NULL
LEFT JOIN oa.sys_dict_type dict_type
    ON dict_type.indicator_code = 'case_type'
    AND dict_type.deleted_at IS NULL
LEFT JOIN oa.sys_dict_item dt_type
    ON dt_type.dict_type_id = dict_type.id
    AND dt_type.item_value = l.case_type::text
    AND dt_type.deleted_at IS NULL
WHERE apt.deleted_at IS NULL;
