-- v1 占位业务 SQL，案件进度看板。
-- TODO: case_name 目前用 case_title 占位；overdue_flag 需要根据当前日期和下一期限计算。
WITH latest_status AS (
    SELECT DISTINCT ON (csl.case_id)
        csl.case_id,
        csl.to_stage AS current_stage,
        csl.to_status AS case_status,
        csl.changed_at AS latest_progress_time
    FROM oa.case_status_log csl
    WHERE csl.deleted_at IS NULL
    ORDER BY csl.case_id, csl.changed_at DESC
),
next_deadline AS (
    SELECT DISTINCT ON (ld.case_id)
        ld.case_id,
        ld.deadline_time::date AS next_deadline_date
    FROM oa.legal_deadline ld
    WHERE ld.deleted_at IS NULL
      AND ld.deadline_status IN ('pending', 'not_started')
    ORDER BY ld.case_id, ld.deadline_time ASC
)
SELECT
    c.id AS case_id,
    c.case_no,
    c.case_title AS case_name,
    COALESCE(dt_type.item_label, c.case_type::text) AS case_type,
    ls.current_stage,
    ls.case_status,
    c.main_lawyer_id AS responsible_lawyer_id,
    c.case_manager_id,
    ls.latest_progress_time,
    nd.next_deadline_date,
    CASE
        WHEN nd.next_deadline_date IS NOT NULL AND nd.next_deadline_date < CURRENT_DATE THEN 1::smallint
        ELSE 0::smallint
    END AS overdue_flag
FROM oa.case_main c
LEFT JOIN latest_status ls ON ls.case_id = c.id
LEFT JOIN next_deadline nd ON nd.case_id = c.id
LEFT JOIN oa.sys_dict_type dict_type
    ON dict_type.indicator_code = 'case_type'
    AND dict_type.deleted_at IS NULL
LEFT JOIN oa.sys_dict_item dt_type
    ON dt_type.dict_type_id = dict_type.id
    AND dt_type.item_value = c.case_type::text
    AND dt_type.deleted_at IS NULL
WHERE c.deleted_at IS NULL;
