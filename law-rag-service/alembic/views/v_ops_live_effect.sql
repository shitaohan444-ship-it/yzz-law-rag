-- v1 占位业务 SQL，按直播场次聚合直播效果。
-- TODO: 需要根据实际线索来源归因规则调整 campaign_id、线索、成交、回款的关联口径。
SELECT
    ls.id AS session_id,
    ls.created_at::date AS live_date,
    ls.platform,
    COALESCE(touch.campaign_id, 0::bigint) AS campaign_id,
    COALESCE(ls.exposure_count, 0) AS exposure_count,
    COALESCE(ls.entry_user_count, 0) AS inquiry_count,
    COALESCE(ls.lead_count, 0) AS lead_count,
    COALESCE(ls.valid_lead_count, 0) AS valid_lead_count,
    COUNT(DISTINCT apt.id) AS appointment_count,
    COUNT(DISTINCT CASE WHEN l.lead_status = 'deal' THEN l.id END) AS deal_count,
    COALESCE(SUM(pr.received_amount), 0::numeric) AS paid_amount
FROM oa.ops_live_session ls
LEFT JOIN oa.lead_source_touch touch
    ON touch.asset_id = ls.id
    AND touch.is_first_touch = 1
    AND touch.deleted_at IS NULL
LEFT JOIN oa.crm_lead l
    ON l.case_source = 2
    AND l.created_at BETWEEN ls.created_at AND ls.created_at + INTERVAL '7 days'
    AND l.deleted_at IS NULL
LEFT JOIN oa.mkt_appointment apt
    ON apt.lead_id = l.id
    AND apt.deleted_at IS NULL
LEFT JOIN oa.fin_payment_record pr
    ON pr.case_id IN (
        SELECT c.id FROM oa.case_main c WHERE c.client_id = l.client_id AND c.deleted_at IS NULL
    )
    AND pr.deleted_at IS NULL
WHERE ls.deleted_at IS NULL
GROUP BY
    ls.id,
    ls.created_at,
    ls.platform,
    touch.campaign_id,
    ls.exposure_count,
    ls.entry_user_count,
    ls.lead_count,
    ls.valid_lead_count;
