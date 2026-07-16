-- v1 占位业务 SQL，按通话记录+线索还原市场电邀台账。
-- TODO: case_source 名称需要从字典转换；deal_intention 名称也需要从字典转换。
SELECT
    l.id AS lead_id,
    call.id AS call_record_id,
    call.call_start_time AS call_time,
    pm.party_name,
    pm.mobile AS party_phone,
    COALESCE(dt_type.item_label, l.case_type::text) AS case_type,
    l.case_brief,
    COALESCE(dt_source.item_label, l.case_source::text) AS case_source,
    l.offline_expand_remark,
    emp.real_name AS consultant_name,
    l.wechat_added_flag,
    l.key_case_flag,
    COALESCE(dt_intention.item_label, l.deal_intention::text) AS deal_intention,
    l.remark
FROM oa.mkt_call_record call
INNER JOIN oa.crm_lead l
    ON l.id = call.lead_id
    AND l.deleted_at IS NULL
LEFT JOIN oa.party_main pm
    ON pm.id = l.primary_party_id
    AND pm.deleted_at IS NULL
LEFT JOIN oa.sys_employee emp
    ON emp.id = call.caller_employee_id
    AND emp.deleted_at IS NULL
LEFT JOIN oa.sys_dict_type dict_type
    ON dict_type.indicator_code = 'case_type'
    AND dict_type.deleted_at IS NULL
LEFT JOIN oa.sys_dict_item dt_type
    ON dt_type.dict_type_id = dict_type.id
    AND dt_type.item_value = l.case_type::text
    AND dt_type.deleted_at IS NULL
LEFT JOIN oa.sys_dict_type dict_source
    ON dict_source.indicator_code = 'case_source'
    AND dict_source.deleted_at IS NULL
LEFT JOIN oa.sys_dict_item dt_source
    ON dt_source.dict_type_id = dict_source.id
    AND dt_source.item_value = l.case_source::text
    AND dt_source.deleted_at IS NULL
LEFT JOIN oa.sys_dict_type dict_intention
    ON dict_intention.indicator_code = 'deal_intention'
    AND dict_intention.deleted_at IS NULL
LEFT JOIN oa.sys_dict_item dt_intention
    ON dt_intention.dict_type_id = dict_intention.id
    AND dt_intention.item_value = l.deal_intention::text
    AND dt_intention.deleted_at IS NULL
WHERE call.deleted_at IS NULL;
