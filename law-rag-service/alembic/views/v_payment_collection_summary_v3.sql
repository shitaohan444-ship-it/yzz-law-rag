-- v3 更新：fin_fee_agreement.deal_amount 重命名为 agreement_amount。
WITH payment_summary AS (
    SELECT
        pp.fee_agreement_id,
        COALESCE(SUM(pp.receivable_amount), 0::numeric) AS receivable_amount,
        COALESCE(SUM(pp.received_amount), 0::numeric) AS received_amount,
        COALESCE(MAX(pp.payment_node_status::text), '') AS payment_node_status
    FROM oa.fin_payment_plan pp
    WHERE pp.deleted_at IS NULL
    GROUP BY pp.fee_agreement_id
),
payment_date AS (
    SELECT
        pp.fee_agreement_id,
        MAX(pr.received_at::date) AS latest_payment_date
    FROM oa.fin_payment_plan pp
    LEFT JOIN oa.fin_payment_record pr
        ON pr.payment_plan_id = pp.id
        AND pr.deleted_at IS NULL
    WHERE pp.deleted_at IS NULL
    GROUP BY pp.fee_agreement_id
),
invoice_summary AS (
    SELECT
        inv.case_id,
        COALESCE(SUM(inv.invoice_amount), 0::numeric) AS invoice_amount
    FROM oa.fin_invoice inv
    WHERE inv.deleted_at IS NULL
    GROUP BY inv.case_id
),
refund_summary AS (
    SELECT
        rr.case_id,
        COALESCE(SUM(rr.refund_amount), 0::numeric) AS refund_amount
    FROM oa.fin_refund_record rr
    WHERE rr.deleted_at IS NULL
    GROUP BY rr.case_id
)
SELECT
    fa.case_id,
    fa.id AS contract_id,
    COALESCE(fa.agreement_amount, 0::numeric) AS contract_amount,
    COALESCE(ps.receivable_amount, 0::numeric) AS receivable_amount,
    COALESCE(ps.received_amount, 0::numeric) AS paid_amount,
    COALESCE(ps.receivable_amount - ps.received_amount, 0::numeric) AS unpaid_amount,
    COALESCE(inv.invoice_amount, 0::numeric) AS invoice_amount,
    COALESCE(rr.refund_amount, 0::numeric) AS refund_amount,
    COALESCE(ps.payment_node_status, '') AS payment_node_status,
    pd.latest_payment_date
FROM oa.fin_fee_agreement fa
LEFT JOIN payment_summary ps ON ps.fee_agreement_id = fa.id
LEFT JOIN payment_date pd ON pd.fee_agreement_id = fa.id
LEFT JOIN invoice_summary inv ON inv.case_id = fa.case_id
LEFT JOIN refund_summary rr ON rr.case_id = fa.case_id
WHERE fa.deleted_at IS NULL;
