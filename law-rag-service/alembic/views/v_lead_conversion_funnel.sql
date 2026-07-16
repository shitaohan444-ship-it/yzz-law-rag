-- v1 占位业务 SQL，按日期+渠道统计线索转化漏斗。
-- TODO: channel_id 目前用 crm_lead.case_source 占位，需要按实际渠道定义调整。
SELECT
    l.created_at::date AS stat_date,
    l.case_source::bigint AS channel_id,
    COALESCE(dict_item.item_label, l.case_source::text, '未知') AS channel_name,
    COUNT(DISTINCT l.id) AS lead_count,
    COUNT(DISTINCT CASE WHEN l.assigned_at IS NOT NULL THEN l.id END) AS assigned_count,
    COUNT(DISTINCT call.id) AS call_count,
    COUNT(DISTINCT apt.id) AS appointment_count,
    COUNT(DISTINCT CASE WHEN apt.actual_arrival_time IS NOT NULL THEN apt.id END) AS visit_count,
    COUNT(DISTINCT neg.id) AS negotiation_count,
    COUNT(DISTINCT CASE WHEN l.lead_status = 'deal' THEN l.id END) AS deal_count,
    COALESCE(SUM(pr.received_amount), 0::numeric) AS paid_amount
FROM oa.crm_lead l
LEFT JOIN oa.sys_dict_type dict_type
    ON dict_type.indicator_code = 'case_source'
    AND dict_type.deleted_at IS NULL
LEFT JOIN oa.sys_dict_item dict_item
    ON dict_item.dict_type_id = dict_type.id
    AND dict_item.item_value = l.case_source::text
    AND dict_item.deleted_at IS NULL
LEFT JOIN oa.mkt_call_record call
    ON call.lead_id = l.id
    AND call.deleted_at IS NULL
LEFT JOIN oa.mkt_appointment apt
    ON apt.lead_id = l.id
    AND apt.deleted_at IS NULL
LEFT JOIN oa.lead_negotiation_record neg
    ON neg.lead_id = l.id
    AND neg.deleted_at IS NULL
LEFT JOIN oa.fin_payment_record pr
    ON pr.case_id IN (
        SELECT c.id FROM oa.case_main c WHERE c.client_id = l.client_id AND c.deleted_at IS NULL
    )
    AND pr.deleted_at IS NULL
WHERE l.deleted_at IS NULL
GROUP BY
    l.created_at::date,
    l.case_source,
    dict_type.id,
    dict_item.item_label;
