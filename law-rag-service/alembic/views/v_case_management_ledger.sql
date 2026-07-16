-- v1 占位业务 SQL，案管部案件综合台账。
-- TODO: 大量字段依赖业务口径确认，如邀约人员、谈案人员、律师角色汇总、付款节点拼接等。
WITH lawyer_agg AS (
    SELECT
        ca.case_id,
        ca.assigned_role,
        STRING_AGG(DISTINCT emp.real_name, ', ' ORDER BY emp.real_name) AS lawyer_names
    FROM oa.case_assignment ca
    LEFT JOIN oa.sys_employee emp ON emp.id = ca.employee_id AND emp.deleted_at IS NULL
    WHERE ca.deleted_at IS NULL
    GROUP BY ca.case_id, ca.assigned_role
),
retrieval_agg AS (
    SELECT
        rt.case_id,
        COUNT(*) AS task_count,
        STRING_AGG(DISTINCT emp.real_name, ', ') AS lawyer_names,
        STRING_AGG(DISTINCT rt.target_unit_type, ', ') AS unit_types,
        STRING_AGG(DISTINCT rt.target_unit_name, ', ') AS unit_names,
        STRING_AGG(DISTINCT rt.retrieval_matter, '; ') AS matters,
        MAX(rt.deadline_at) AS deadline_at,
        STRING_AGG(DISTINCT rt.task_status, ', ') AS task_status,
        STRING_AGG(DISTINCT rt.result_status, ', ') AS result_status,
        STRING_AGG(DISTINCT rt.remark, '; ') AS remarks,
        STRING_AGG(DISTINCT rt.nas_path, '; ') AS nas_paths
    FROM oa.case_retrieval_task rt
    LEFT JOIN oa.sys_employee emp ON emp.id = rt.assigned_lawyer_id AND emp.deleted_at IS NULL
    WHERE rt.deleted_at IS NULL
    GROUP BY rt.case_id
),
latest_retrieval_log AS (
    SELECT DISTINCT ON (rtl.case_id)
        rtl.case_id,
        rtl.content AS latest_log
    FROM oa.case_retrieval_task_log rtl
    WHERE rtl.deleted_at IS NULL
    ORDER BY rtl.case_id, rtl.operated_at DESC
),
payment_agg AS (
    SELECT
        pp.case_id,
        STRING_AGG(DISTINCT pp.plan_name || '（' || pp.receivable_amount::text || '）', '; ') AS payment_nodes,
        COALESCE(SUM(pp.received_amount), 0::numeric) AS paid_amount,
        COALESCE(SUM(pp.receivable_amount), 0::numeric) AS receivable_amount
    FROM oa.fin_payment_plan pp
    WHERE pp.deleted_at IS NULL
    GROUP BY pp.case_id
),
invoice_agg AS (
    SELECT
        inv.case_id,
        COALESCE(SUM(inv.invoice_amount), 0::numeric) AS invoice_amount,
        MAX(CASE WHEN inv.invoice_status = 'issued' THEN 1 ELSE 0 END) AS has_issued_invoice
    FROM oa.fin_invoice inv
    WHERE inv.deleted_at IS NULL
    GROUP BY inv.case_id
),
refund_agg AS (
    SELECT
        rr.case_id,
        COALESCE(SUM(rr.refund_amount), 0::numeric) AS refund_amount
    FROM oa.fin_refund_record rr
    WHERE rr.deleted_at IS NULL
    GROUP BY rr.case_id
),
latest_status AS (
    SELECT DISTINCT ON (csl.case_id)
        csl.case_id,
        csl.to_stage AS case_stage,
        csl.to_status AS case_status,
        csl.changed_at AS stage_time,
        csl.progress_summary
    FROM oa.case_status_log csl
    WHERE csl.deleted_at IS NULL
    ORDER BY csl.case_id, csl.changed_at DESC
)
SELECT
    TO_CHAR(COALESCE(c.accept_date, c.created_at), 'YYYY-MM') AS stat_month,
    COALESCE(ls.case_status::varchar(80), '') AS case_status,
    c.case_no,
    c.accept_date AS entrust_date,
    c.case_type,
    cl.profile_summary AS client_name,
    COALESCE(pm.party_name, cl.profile_summary) AS party_name,
    ''::varchar(500) AS inviter_employee_names,
    ''::varchar(500) AS negotiator_employee_names,
    COALESCE(la_main.lawyer_names, '') AS practicing_lawyer_names,
    COALESCE(la_trainee.lawyer_names, '') AS trainee_lawyer_names,
    c.lawyer_assistant_name,
    ls.case_stage::varchar(80) AS case_stage,
    ls.stage_time,
    ''::varchar(200) AS work_node,
    ls.progress_summary,
    COALESCE(pa.payment_nodes, '') AS payment_node,
    COALESCE(fa.deal_amount / 10000.0, 0::numeric) AS deal_amount_wan,
    0::numeric AS monthly_received_amount_wan,
    COALESCE(pa.paid_amount / 10000.0, 0::numeric) AS paid_amount_wan,
    COALESCE((pa.receivable_amount - pa.paid_amount) / 10000.0, 0::numeric) AS unpaid_amount_wan,
    COALESCE(ra.refund_amount / 10000.0, 0::numeric) AS refund_amount_wan,
    NULL::smallint AS refund_reason_type,
    CASE WHEN ia.has_issued_invoice = 1 THEN 1::smallint ELSE 0::smallint END AS invoice_status,
    COALESCE(ia.invoice_amount / 10000.0, 0::numeric) AS invoice_amount_wan,
    c.remark,
    CASE WHEN rt.task_count > 0 THEN 1::smallint ELSE 0::smallint END AS has_retrieval_task,
    COALESCE(rt.task_count, 0)::integer AS retrieval_task_count,
    COALESCE(rt.task_status, '') AS retrieval_task_status,
    COALESCE(rt.lawyer_names, '') AS retrieval_lawyer_names,
    COALESCE(rt.unit_types, '') AS retrieval_unit_type,
    COALESCE(rt.unit_names, '') AS retrieval_unit_name,
    COALESCE(rt.matters, '') AS retrieval_matter,
    rt.deadline_at AS retrieval_deadline_at,
    COALESCE(rt.result_status, '') AS retrieval_result_status,
    COALESCE(rt.remarks, '') AS retrieval_remark,
    COALESCE(lrl.latest_log, '') AS latest_retrieval_log,
    COALESCE(rt.nas_paths, '') AS retrieval_nas_path
FROM oa.case_main c
LEFT JOIN oa.crm_client cl ON cl.id = c.client_id AND cl.deleted_at IS NULL
LEFT JOIN oa.party_main pm ON pm.id = c.client_id AND pm.deleted_at IS NULL
LEFT JOIN latest_status ls ON ls.case_id = c.id
LEFT JOIN lawyer_agg la_main ON la_main.case_id = c.id AND la_main.assigned_role = 'main_lawyer'
LEFT JOIN lawyer_agg la_trainee ON la_trainee.case_id = c.id AND la_trainee.assigned_role = 'trainee'
LEFT JOIN payment_agg pa ON pa.case_id = c.id
LEFT JOIN fin_fee_agreement fa ON fa.case_id = c.id AND fa.deleted_at IS NULL
LEFT JOIN invoice_agg ia ON ia.case_id = c.id
LEFT JOIN refund_agg ra ON ra.case_id = c.id
LEFT JOIN retrieval_agg rt ON rt.case_id = c.id
LEFT JOIN latest_retrieval_log lrl ON lrl.case_id = c.id
WHERE c.deleted_at IS NULL;
