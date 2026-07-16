-- v1 占位业务 SQL，按投放日消耗聚合运营渠道日报。
-- TODO: 主播字段目前用 campaign 负责人占位，后续需要按实际直播场次主播关联。
SELECT
    d.spend_date AS report_date,
    COALESCE(d.platform_snapshot, camp.platform::text, '未知') AS platform_name,
    d.live_session_id,
    camp.owner_employee_id AS host_employee_id,
    emp.real_name AS host_name,
    COALESCE(d.ad_cost, 0::numeric) AS ad_cost,
    COALESCE(d.lead_count, 0) AS lead_count,
    CASE
        WHEN COALESCE(d.lead_count, 0) = 0 THEN 0::numeric
        ELSE ROUND(d.ad_cost / NULLIF(d.lead_count, 0), 2)
    END AS cost_per_lead,
    COALESCE(d.exposure_count, 0) AS exposure_count,
    COALESCE(d.cumulative_viewer_count, 0) AS cumulative_viewer_count,
    d.remark
FROM oa.ops_ad_spend_daily d
LEFT JOIN oa.ops_ad_campaign camp
    ON camp.id = d.campaign_id
    AND camp.deleted_at IS NULL
LEFT JOIN oa.sys_employee emp
    ON emp.id = camp.owner_employee_id
    AND emp.deleted_at IS NULL
LEFT JOIN oa.ops_live_session ls
    ON ls.id = d.live_session_id
    AND ls.deleted_at IS NULL
WHERE d.deleted_at IS NULL;
