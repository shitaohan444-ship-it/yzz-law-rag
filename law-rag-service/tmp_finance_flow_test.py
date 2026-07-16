"""
财务部整体流程测试数据。
场景：复用钱七离婚财产分割案（case_id=9），验证回款确认、发票开具、回款跟进、退费审批。
脚本支持重复运行：每次运行会先清理带有 FIN_TEST 标记的历史测试数据。
"""
from datetime import datetime, date, timezone, timedelta
from sqlalchemy import create_engine, text
from app.core.config import settings

engine = create_engine(settings.database_url_with_search_path, future=True)

now = datetime.now(timezone.utc)
today = date.today()
next_week = today + timedelta(days=7)

# 测试业务常量
CASE_ID = 9
CLIENT_ID = 27
FEE_AGREEMENT_ID = 9
PP_SIGN = 14           # 签约首付款（已有真实回款 5,000）
PP_FILING = 15         # 立案阶段款（待回款 15,000）
PP_FINAL = 16          # 判决生效尾款（待回款 30,000）
DEPT_FINANCE = 4       # 财务部
EMP_FINANCE = 7        # 财务专员
TEST_MARKER = "[FIN_TEST]"


def cleanup_previous_test_data(conn):
    """清理上一次测试运行产生的标记数据，并还原对应的回款计划状态。"""
    # 1. 删除测试回款记录，并扣减对应回款计划的已收金额
    deleted_payments = conn.execute(
        text("""
            DELETE FROM oa.fin_payment_record
            WHERE case_id = :case_id AND bank_flow_no LIKE 'FIN_TEST_%'
            RETURNING payment_plan_id, received_amount
        """),
        {"case_id": CASE_ID},
    ).mappings().all()

    for row in deleted_payments:
        conn.execute(
            text("""
                UPDATE oa.fin_payment_plan
                SET received_amount = GREATEST(received_amount - :amount, 0),
                    payment_node_status = CASE
                        WHEN (received_amount - :amount) <= 0 THEN 0
                        ELSE 2
                    END,
                    last_follow_time = NULL,
                    updated_at = :now
                WHERE id = :pp_id
            """),
            {
                "amount": row["received_amount"],
                "pp_id": row["payment_plan_id"],
                "now": now,
            },
        )

    # 2. 删除测试发票
    conn.execute(
        text("""
            DELETE FROM oa.fin_invoice
            WHERE case_id = :case_id AND invoice_no LIKE 'FIN_TEST_%'
        """),
        {"case_id": CASE_ID},
    )

    # 3. 删除测试退费记录及其关联审批记录
    refund_ids = conn.execute(
        text("""
            SELECT id FROM oa.fin_refund_record
            WHERE case_id = :case_id AND remark LIKE :marker
        """),
        {"case_id": CASE_ID, "marker": f"%{TEST_MARKER}%"},
    ).scalars().all()

    if refund_ids:
        # 先删子表退费记录，再删父表审批记录（存在外键约束）
        approval_ids = conn.execute(
            text("""
                SELECT DISTINCT approval_record_id
                FROM oa.fin_refund_record
                WHERE id = ANY(:ids) AND approval_record_id IS NOT NULL
            """),
            {"ids": refund_ids},
        ).scalars().all()

        conn.execute(
            text("DELETE FROM oa.fin_refund_record WHERE id = ANY(:ids)"),
            {"ids": refund_ids},
        )

        if approval_ids:
            conn.execute(
                text("""
                    DELETE FROM oa.sys_approval_record
                    WHERE approval_type = 'refund'
                      AND remark LIKE :marker
                      AND id = ANY(:ids)
                """),
                {"marker": f"%{TEST_MARKER}%", "ids": approval_ids},
            )

    # 4. 删除测试回款跟进记录
    conn.execute(
        text("""
            DELETE FROM oa.fin_payment_followup
            WHERE case_id = :case_id AND followup_content LIKE :marker
        """),
        {"case_id": CASE_ID, "marker": f"%{TEST_MARKER}%"},
    )


def ensure_finance_employee(conn):
    """确保存在财务部及财务人员；若不存在则插入。"""
    dept_exists = conn.execute(
        text("SELECT 1 FROM oa.sys_department WHERE id = :id"),
        {"id": DEPT_FINANCE},
    ).scalar()
    if not dept_exists:
        conn.execute(
            text("""
                INSERT INTO oa.sys_department (
                    id, department_code, department_name, status, created_at, updated_at
                ) VALUES (
                    :id, 'FIN', '财务部', 'active', :now, :now
                )
            """),
            {"id": DEPT_FINANCE, "now": now},
        )

    emp_exists = conn.execute(
        text("SELECT 1 FROM oa.sys_employee WHERE id = :id"),
        {"id": EMP_FINANCE},
    ).scalar()
    if not emp_exists:
        conn.execute(
            text("""
                INSERT INTO oa.sys_employee (
                    id, employee_no, real_name, department_id, position_name,
                    employment_status, created_at, updated_at
                ) VALUES (
                    :id, 'E007', '财务专员', :dept_id, '财务专员',
                    'active', :now, :now
                )
            """),
            {"id": EMP_FINANCE, "dept_id": DEPT_FINANCE, "now": now},
        )


with engine.begin() as conn:
    # ============================================================
    # 0. 环境准备
    # ============================================================
    cleanup_previous_test_data(conn)
    ensure_finance_employee(conn)

    # ============================================================
    # 1. 回款跟进：对立案阶段款进行到期前催收
    # ============================================================
    conn.execute(
        text("""
            INSERT INTO oa.fin_payment_followup (
                payment_plan_id, fee_agreement_id, case_id, client_id,
                followup_employee_id, followup_department_id, followup_time,
                followup_method, followup_content, customer_feedback,
                followup_result, next_followup_time, is_overdue, overdue_days,
                created_at, created_by, updated_at, status
            ) VALUES (
                :pp_id, :fa_id, :case_id, :client_id,
                :emp_id, :dept_id, :now,
                '电话', :content, '客户表示近期安排付款',
                '承诺付款', :next_week, false, 0,
                :now, :emp_id, :now, 'active'
            )
        """),
        {
            "pp_id": PP_FILING,
            "fa_id": FEE_AGREEMENT_ID,
            "case_id": CASE_ID,
            "client_id": CLIENT_ID,
            "emp_id": EMP_FINANCE,
            "dept_id": DEPT_FINANCE,
            "now": now,
            "next_week": next_week,
            "content": f"催收立案阶段款 15,000 元 {TEST_MARKER}",
        },
    )

    # ============================================================
    # 2. 立案阶段款回款确认
    # ============================================================
    conn.execute(
        text("""
            INSERT INTO oa.fin_payment_record (
                payment_plan_id, case_id, client_id, received_amount, received_at,
                payment_method, payer_name, bank_flow_no, confirm_status,
                remark, created_at, updated_at, status
            ) VALUES (
                :pp_id, :case_id, :client_id, 15000.00, :now,
                'bank_transfer', '钱七', :bank_flow, 'confirmed',
                :remark, :now, :now, 'active'
            )
        """),
        {
            "pp_id": PP_FILING,
            "case_id": CASE_ID,
            "client_id": CLIENT_ID,
            "now": now,
            "bank_flow": f"FIN_TEST_FILING_{today.strftime('%Y%m%d')}",
            "remark": f"立案阶段款到账 {TEST_MARKER}",
        },
    )

    conn.execute(
        text("""
            UPDATE oa.fin_payment_plan
            SET received_amount = 15000.00,
                payment_node_status = 2,
                last_follow_time = :now,
                updated_at = :now
            WHERE id = :pp_id
        """),
        {"pp_id": PP_FILING, "now": now},
    )

    # ============================================================
    # 3. 判决生效尾款回款确认
    # ============================================================
    conn.execute(
        text("""
            INSERT INTO oa.fin_payment_record (
                payment_plan_id, case_id, client_id, received_amount, received_at,
                payment_method, payer_name, bank_flow_no, confirm_status,
                remark, created_at, updated_at, status
            ) VALUES (
                :pp_id, :case_id, :client_id, 30000.00, :now,
                'bank_transfer', '钱七', :bank_flow, 'confirmed',
                :remark, :now, :now, 'active'
            )
        """),
        {
            "pp_id": PP_FINAL,
            "case_id": CASE_ID,
            "client_id": CLIENT_ID,
            "now": now,
            "bank_flow": f"FIN_TEST_FINAL_{today.strftime('%Y%m%d')}",
            "remark": f"判决生效尾款到账 {TEST_MARKER}",
        },
    )

    conn.execute(
        text("""
            UPDATE oa.fin_payment_plan
            SET received_amount = 30000.00,
                payment_node_status = 2,
                last_follow_time = :now,
                updated_at = :now
            WHERE id = :pp_id
        """),
        {"pp_id": PP_FINAL, "now": now},
    )

    # ============================================================
    # 4. 开具发票
    # ============================================================
    conn.execute(
        text("""
            INSERT INTO oa.fin_invoice (
                case_id, client_id, invoice_title, tax_no, invoice_type,
                invoice_amount, invoice_status, invoice_no, issued_at,
                created_at, updated_at, status, remark
            ) VALUES (
                :case_id, :client_id, '钱七', '320722198001011234', 'service',
                15000.00, 'issued', :invoice_no, :now,
                :now, :now, 'active', :remark
            )
        """),
        {
            "case_id": CASE_ID,
            "client_id": CLIENT_ID,
            "now": now,
            "invoice_no": f"FIN_TEST_I_FILING_{today.strftime('%Y%m%d')}",
            "remark": f"立案阶段款发票 {TEST_MARKER}",
        },
    )

    conn.execute(
        text("""
            INSERT INTO oa.fin_invoice (
                case_id, client_id, invoice_title, tax_no, invoice_type,
                invoice_amount, invoice_status, invoice_no, issued_at,
                created_at, updated_at, status, remark
            ) VALUES (
                :case_id, :client_id, '钱七', '320722198001011234', 'service',
                30000.00, 'issued', :invoice_no, :now,
                :now, :now, 'active', :remark
            )
        """),
        {
            "case_id": CASE_ID,
            "client_id": CLIENT_ID,
            "now": now,
            "invoice_no": f"FIN_TEST_I_FINAL_{today.strftime('%Y%m%d')}",
            "remark": f"判决生效尾款发票 {TEST_MARKER}",
        },
    )

    # ============================================================
    # 5. 退费审批流程
    # ============================================================
    approval_id = conn.execute(
        text("""
            INSERT INTO oa.sys_approval_record (
                approval_no, approval_type, applicant_employee_id,
                approver_employee_id, approval_opinion, approval_status,
                created_at, created_by, updated_at, updated_by,
                status, remark
            ) VALUES (
                :approval_no, 'refund', :applicant,
                :approver, '同意退费', 'approved',
                :now, :applicant, :now, :approver,
                'active', :remark
            )
            RETURNING id
        """),
        {
            "approval_no": f"FIN_TEST_APPR_{today.strftime('%Y%m%d')}",
            "applicant": EMP_FINANCE,
            "approver": EMP_FINANCE,
            "now": now,
            "remark": f"钱七案件退费审批 {TEST_MARKER}",
        },
    ).scalar()

    conn.execute(
        text("""
            INSERT INTO oa.fin_refund_record (
                case_id, fee_agreement_id, refund_amount, refund_reason_type,
                refund_reason_detail, refund_date, approval_record_id,
                refund_status, created_by, created_at, updated_at, remark
            ) VALUES (
                :case_id, :fa_id, 2000.00, 3,
                '协商部分退费', :today, :approval_id,
                3, :emp_id, :now, :now, :remark
            )
        """),
        {
            "case_id": CASE_ID,
            "fa_id": FEE_AGREEMENT_ID,
            "today": today,
            "approval_id": approval_id,
            "emp_id": EMP_FINANCE,
            "now": now,
            "remark": f"退费 2,000 元 {TEST_MARKER}",
        },
    )

    # ============================================================
    # 6. 结果校验
    # ============================================================
    summary = conn.execute(
        text("""
            SELECT contract_amount, receivable_amount, paid_amount,
                   unpaid_amount, invoice_amount, refund_amount
            FROM oa.v_payment_collection_summary
            WHERE case_id = :case_id AND contract_id = :contract_id
        """),
        {"case_id": CASE_ID, "contract_id": FEE_AGREEMENT_ID},
    ).mappings().one()

    print("=" * 50)
    print("财务部整体流程测试完成")
    print("=" * 50)
    print(f"合同金额: {summary['contract_amount']}")
    print(f"应收金额: {summary['receivable_amount']}")
    print(f"实收金额: {summary['paid_amount']}")
    print(f"未收金额: {summary['unpaid_amount']}")
    print(f"开票金额: {summary['invoice_amount']}")
    print(f"退费金额: {summary['refund_amount']}")

    # 简单断言
    assert summary["contract_amount"] == 50000.00
    assert summary["receivable_amount"] == 50000.00
    assert summary["paid_amount"] == 50000.00
    assert summary["unpaid_amount"] == 0.00
    assert summary["invoice_amount"] == 50000.00  # 5,000 原有 + 15,000 + 30,000 测试发票
    assert summary["refund_amount"] == 3000.00    # 1,000 原有 + 2,000 测试退费
    print("所有校验通过")
