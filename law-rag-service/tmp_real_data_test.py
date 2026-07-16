"""
插入一组真实、全面的律所 OA 流程测试数据。
场景：李四通过抖音直播间咨询交通事故赔偿案件，最终签约并进入诉讼流程。

本脚本支持重复运行：每次运行会先按业务主键清理上一轮插入的测试数据，
并基于当前最大员工编号自动生成协办律师、实习律师的 employee_no。
"""
from datetime import datetime, date, timezone, timedelta
from decimal import Decimal
from sqlalchemy import create_engine, text
from app.core.config import settings

engine = create_engine(settings.database_url_with_search_path, future=True)

now = datetime.now(timezone.utc)
today = date.today()
yesterday = today - timedelta(days=1)
tomorrow = today + timedelta(days=1)
next_week = today + timedelta(days=7)

# 现有基础数据 ID
DEPT_MARKET = 1      # 市场拓展部
DEPT_CASE = 2        # 案件管理部
DEPT_LAWYER = 3      # 律师部
EMP_MARKET = 1       # 张三 市场专员
EMP_MARKET_2 = 2     # 李四 市场专员（协助）
EMP_CASE_MGR = 3     # 王五 案管专员
EMP_LAWYER_MAIN = 4  # 赵六 主办律师

# 本脚本生成的业务主键（用于幂等清理）
PARTY_CODE = 'P20260709001'
CLIENT_NO = 'C20260709001'
LEAD_NO = 'L20260709001'
CASE_NO = 'C20260709001'
AGREEMENT_NO = 'A20260709001'
CALL_TASK_NAME = '7.8直播线索回访任务'


def cleanup_previous_test_data(conn) -> None:
    """按业务主键清理上一轮运行产生的测试数据。"""
    # 先通过业务主键定位到相关实体 ID
    party_id = conn.execute(
        text("SELECT id FROM oa.party_main WHERE party_code = :code"),
        {"code": PARTY_CODE},
    ).scalar()
    client_id = conn.execute(
        text("SELECT id FROM oa.crm_client WHERE client_no = :no"),
        {"no": CLIENT_NO},
    ).scalar()
    lead_id = conn.execute(
        text("SELECT id FROM oa.crm_lead WHERE lead_no = :no"),
        {"no": LEAD_NO},
    ).scalar()
    case_id = conn.execute(
        text("SELECT id FROM oa.case_main WHERE case_no = :no"),
        {"no": CASE_NO},
    ).scalar()
    fee_agreement_id = conn.execute(
        text("SELECT id FROM oa.fin_fee_agreement WHERE agreement_no = :no"),
        {"no": AGREEMENT_NO},
    ).scalar()

    # 按外键依赖反向删除案件相关子表
    if case_id:
        conn.execute(text("DELETE FROM oa.evidence_item WHERE case_id = :case_id"), {"case_id": case_id})
        conn.execute(text("DELETE FROM oa.court_hearing WHERE case_id = :case_id"), {"case_id": case_id})
        conn.execute(text("DELETE FROM oa.legal_deadline WHERE case_id = :case_id"), {"case_id": case_id})
        conn.execute(text("DELETE FROM oa.legal_work_log WHERE case_id = :case_id"), {"case_id": case_id})
        conn.execute(text("DELETE FROM oa.case_retrieval_task WHERE case_id = :case_id"), {"case_id": case_id})
        conn.execute(text("DELETE FROM oa.fin_invoice WHERE case_id = :case_id"), {"case_id": case_id})
        conn.execute(text("DELETE FROM oa.fin_payment_record WHERE case_id = :case_id"), {"case_id": case_id})
        conn.execute(text("DELETE FROM oa.fin_payment_plan WHERE case_id = :case_id"), {"case_id": case_id})
        conn.execute(text("DELETE FROM oa.case_status_log WHERE case_id = :case_id"), {"case_id": case_id})
        conn.execute(text("DELETE FROM oa.case_assignment WHERE case_id = :case_id"), {"case_id": case_id})
        conn.execute(text("DELETE FROM oa.case_party WHERE case_id = :case_id"), {"case_id": case_id})
        # case_intake_handover 外键引用 fee_agreement，需先删除
        conn.execute(text("DELETE FROM oa.case_intake_handover WHERE case_id = :case_id"), {"case_id": case_id})
        # 收费协议依赖案件，需在 case_main 之前删除
        conn.execute(text("DELETE FROM oa.fin_fee_agreement WHERE case_id = :case_id"), {"case_id": case_id})
        conn.execute(text("DELETE FROM oa.case_main WHERE id = :case_id"), {"case_id": case_id})

    # fee_agreement_id 可能因 case_id 为空（如第一次运行到一半失败）而仍需要单独清理
    if fee_agreement_id:
        conn.execute(text("DELETE FROM oa.fin_fee_agreement WHERE id = :id"), {"id": fee_agreement_id})

    if lead_id:
        conn.execute(text("DELETE FROM oa.lead_assignment_log WHERE lead_id = :lead_id"), {"lead_id": lead_id})
        conn.execute(text("DELETE FROM oa.mkt_call_record WHERE lead_id = :lead_id"), {"lead_id": lead_id})
        # lead_negotiation_record 外键引用 appointment，需先删除
        conn.execute(text("DELETE FROM oa.lead_negotiation_record WHERE lead_id = :lead_id"), {"lead_id": lead_id})
        conn.execute(text("DELETE FROM oa.mkt_appointment WHERE lead_id = :lead_id"), {"lead_id": lead_id})
        conn.execute(text("DELETE FROM oa.crm_lead WHERE id = :lead_id"), {"lead_id": lead_id})

    # 删除本脚本创建的电话任务（不依赖线索）
    conn.execute(text("DELETE FROM oa.mkt_call_task WHERE task_name = :name"), {"name": CALL_TASK_NAME})

    if client_id:
        conn.execute(text("DELETE FROM oa.crm_client WHERE id = :client_id"), {"client_id": client_id})

    if party_id:
        conn.execute(text("DELETE FROM oa.party_main WHERE id = :party_id"), {"party_id": party_id})

    # 最后尝试删除本脚本创建的协办律师和实习律师；
    # 若其他测试脚本仍引用这些员工（如 tmp_case_management_flow_test.py 硬编码 E005/E006），则保留。
    employee_ids = conn.execute(
        text("SELECT id FROM oa.sys_employee WHERE real_name IN ('孙七', '周八')")
    ).scalars().all()
    for emp_id in employee_ids:
        ref_count = conn.execute(
            text("SELECT COUNT(*) FROM oa.case_assignment WHERE employee_id = :emp_id"),
            {"emp_id": emp_id},
        ).scalar()
        if ref_count == 0:
            conn.execute(text("DELETE FROM oa.sys_employee WHERE id = :emp_id"), {"emp_id": emp_id})

    print("[real_data_test] Cleaned existing test data")


def next_employee_no(conn) -> str:
    """基于当前最大 E 编号生成下一个员工编号。"""
    max_no = conn.execute(text("""
        SELECT COALESCE(MAX(CAST(SUBSTRING(employee_no FROM 2) AS INTEGER)), 4)
        FROM oa.sys_employee
        WHERE employee_no LIKE 'E%'
    """)).scalar()
    return f"E{int(max_no) + 1:03d}"


with engine.begin() as conn:
    cleanup_previous_test_data(conn)

    # 先获取当前最大员工 ID，避免 IDENTITY 序列落后导致主键冲突
    max_emp_id = conn.execute(text("SELECT COALESCE(MAX(id), 0) FROM oa.sys_employee")).scalar()
    next_emp_id = int(max_emp_id) + 1

    # 自动生成员工编号，保证重复执行时不冲突
    emp_no_assist = next_employee_no(conn)
    emp_no_trainee = f"E{int(emp_no_assist[1:]) + 1:03d}"

    # 1. 插入协办律师和实习律师
    emp_lawyer_assist = conn.execute(text("""
        INSERT INTO oa.sys_employee (id, employee_no, real_name, gender, department_id, employment_status, join_date, status, created_at, updated_at)
        VALUES (:id, :emp_no, '孙七', 'unknown', :dept_id, 'active', :today, 'active', :now, :now)
        RETURNING id
    """), {"id": next_emp_id, "emp_no": emp_no_assist, "dept_id": DEPT_LAWYER, "today": today, "now": now}).scalar()

    emp_trainee = conn.execute(text("""
        INSERT INTO oa.sys_employee (id, employee_no, real_name, gender, department_id, employment_status, join_date, status, created_at, updated_at)
        VALUES (:id, :emp_no, '周八', 'unknown', :dept_id, 'active', :today, 'active', :now, :now)
        RETURNING id
    """), {"id": next_emp_id + 1, "emp_no": emp_no_trainee, "dept_id": DEPT_LAWYER, "today": today, "now": now}).scalar()

    # 2. 当事人 / 客户
    party_id = conn.execute(text("""
        INSERT INTO oa.party_main (party_code, party_type, party_name, gender, mobile, id_type, id_number, address, is_repeat_party, party_status, is_deleted, created_at, updated_at)
        VALUES (:party_code, 1, '李四', 1, '13900139000', 1, '320722199001011234', '江苏省连云港市海州区', 0, 1, 0, :now, :now)
        RETURNING id
    """), {"party_code": PARTY_CODE, "now": now}).scalar()

    client_id = conn.execute(text("""
        INSERT INTO oa.crm_client (client_no, client_type, id_card_no, client_level, risk_level, privacy_level, profile_summary, owner_employee_id, case_source, status, created_at, updated_at)
        VALUES (:client_no, 'individual', '320722199001011234', 'normal', 'low', 'normal', '李四（交通事故赔偿案件当事人）', :emp_market, 1, 'active', :now, :now)
        RETURNING id
    """), {"client_no": CLIENT_NO, "emp_market": EMP_MARKET, "now": now}).scalar()

    # 3. 线索（来源：抖音直播间，线下拓展备注，主谈人、成交金额等）
    lead_id = conn.execute(text("""
        INSERT INTO oa.crm_lead (
            lead_no, lead_title, case_brief, demand_summary, urgency_level, lead_status,
            case_source, offline_expand_remark, owner_employee_id, owner_department_id,
            main_negotiator_id, assistant_negotiator_id, consultant_employee_id,
            case_type, deal_intention, deal_amount, received_amount, remaining_balance, balance_due_date,
            wechat_added_flag, wechat_added_at, wechat_added_by,
            key_case_flag, key_case_reason, is_duplicate_party, assigned_at, visit_at,
            created_at, updated_at, status
        ) VALUES (
            :lead_no, '李四交通事故赔偿咨询',
            '2026年6月15日，李四驾驶私家车在某路口被货车追尾，造成车辆受损、腰椎挫伤，交警认定对方全责。',
            '希望委托律师起诉对方及保险公司，主张医疗费、误工费、车辆损失、精神损害赔偿等。',
            'high', 'converted',
            1, '抖音直播间-2026.7.8晚间场，用户留言后私信预约到所',
            :emp_market, :dept_market,
            :emp_market, :emp_market_2, :emp_market,
            2, 4, 200000.00, 20000.00, 180000.00, :next_week,
            1, :now, :emp_market,
            1, '标的额较高，涉及多方责任', 0, :yesterday, :now,
            :now, :now, 'active'
        )
        RETURNING id
    """), {
        "lead_no": LEAD_NO,
        "emp_market": EMP_MARKET, "emp_market_2": EMP_MARKET_2,
        "dept_market": DEPT_MARKET, "next_week": next_week,
        "yesterday": yesterday, "now": now
    }).scalar()

    # 4. 线索下发
    conn.execute(text("""
        INSERT INTO oa.lead_assignment_log (lead_id, from_department_id, to_department_id, from_employee_id, to_employee_id, assigned_by, assigned_at, accepted_at, assignment_status, assignment_reason, created_at, updated_at)
        VALUES (:lead_id, :dept_market, :dept_market, :emp_market_2, :emp_market, :emp_market_2, :yesterday, :yesterday, 2, '直播间线索分配给张三跟进', :now, :now)
    """), {"lead_id": lead_id, "dept_market": DEPT_MARKET, "emp_market": EMP_MARKET, "emp_market_2": EMP_MARKET_2, "yesterday": yesterday, "now": now})

    # 5. 电话邀约任务 + 电话记录
    call_task_id = conn.execute(text("""
        INSERT INTO oa.mkt_call_task (task_name, batch_no, case_source, assigned_employee_id, planned_call_time, task_priority, task_status, script_version, planned_count, created_at, updated_at, status)
        VALUES (:task_name, 'T20260708001', 1, :emp_market, :yesterday, 'high', 'completed', 'v1.0', 20, :now, :now, 'active')
        RETURNING id
    """), {"task_name": CALL_TASK_NAME, "emp_market": EMP_MARKET, "yesterday": yesterday, "now": now}).scalar()

    conn.execute(text("""
        INSERT INTO oa.mkt_call_record (call_task_id, lead_id, caller_employee_id, call_direction, call_start_time, call_duration_seconds, call_result, call_connect_result, invitation_result, conversation_summary, next_action, appointment_created, created_at, updated_at)
        VALUES (:call_task_id, :lead_id, :emp_market, 'outbound', :yesterday, 380, 'connected', 'connected', 'visited', '当事人对律所专业能力认可，同意次日到所面谈，已添加微信。', '预约到访', true, :now, :now)
    """), {"call_task_id": call_task_id, "lead_id": lead_id, "emp_market": EMP_MARKET, "yesterday": yesterday, "now": now})

    # 6. 预约到访
    appointment_id = conn.execute(text("""
        INSERT INTO oa.mkt_appointment (client_id, lead_id, appointment_type, appointment_time, actual_arrival_time, reception_employee_id, lawyer_employee_id, legal_category, appointment_status, visit_result, reschedule_count, visit_sequence, appointment_source, confirmation_status, created_at, updated_at, status)
        VALUES (:client_id, :lead_id, 'visit', :yesterday, :yesterday, :emp_market, :emp_market, '交通事故', 'completed', 'signed', 0, 1, 1, 2, :now, :now, 'active')
        RETURNING id
    """), {"client_id": client_id, "lead_id": lead_id, "emp_market": EMP_MARKET, "yesterday": yesterday, "now": now}).scalar()

    # 7. 谈案记录
    negotiation_id = conn.execute(text("""
        INSERT INTO oa.lead_negotiation_record (lead_id, appointment_id, negotiation_time, main_negotiator_id, assistant_negotiator_id, participants, deal_intention, deal_amount, received_amount, customer_objection, negotiation_result, lost_reason_type, next_action, next_follow_up_at, recording_attachment_id, key_case_flag, key_case_reason, payment_terms_snapshot, created_at, updated_at)
        VALUES (:lead_id, :appointment_id, :yesterday, :emp_market, :emp_market_2, '张三、李四、王五（旁听）', 4, 200000.00, 20000.00, '当事人担心诉讼周期长、执行难。', 1, NULL, '签约并移交案管', :today, NULL, 1, '标的额20万，涉及保险理赔', '风险代理：签约时支付2万元，剩余18万元按实际回款金额10%收取。', :now, :now)
        RETURNING id
    """), {"lead_id": lead_id, "appointment_id": appointment_id, "emp_market": EMP_MARKET, "emp_market_2": EMP_MARKET_2, "yesterday": yesterday, "today": today, "now": now}).scalar()

    # 8. 案件主表
    case_id = conn.execute(text("""
        INSERT INTO oa.case_main (case_no, case_title, client_id, case_stage, case_status, court_or_agency, accept_date, filing_date, case_brief, claim_summary, main_lawyer_id, case_manager_id, conflict_check_status, important_level, case_type, created_at, updated_at, status)
        VALUES (:case_no, '李四诉王某某、某保险公司交通事故责任纠纷案', :client_id, 'intake', 'assigned', '连云港市海州区人民法院', :today, :tomorrow, '李四交通事故赔偿案件', '主张医疗费、误工费、护理费、车辆损失、精神损害赔偿合计约20万元。', :emp_lawyer_main, :emp_case_mgr, 'passed', 'important', 2, :now, :now, 'active')
        RETURNING id
    """), {"case_no": CASE_NO, "client_id": client_id, "emp_lawyer_main": EMP_LAWYER_MAIN, "emp_case_mgr": EMP_CASE_MGR, "today": today, "tomorrow": tomorrow, "now": now}).scalar()

    # 9. 收费协议
    fee_agreement_id = conn.execute(text("""
        INSERT INTO oa.fin_fee_agreement (agreement_no, case_id, client_id, contract_no, fee_type, agreement_amount, currency, sign_date, payment_terms, responsible_employee_id, agreement_status, created_at, updated_at, status)
        VALUES (:agreement_no, :case_id, :client_id, 'HT20260709001', 'risk', 200000.00, 'CNY', :today, '签约支付2万元；剩余按回款金额10%收取。', :emp_lawyer_main, 'signed', :now, :now, 'active')
        RETURNING id
    """), {"agreement_no": AGREEMENT_NO, "case_id": case_id, "client_id": client_id, "emp_lawyer_main": EMP_LAWYER_MAIN, "today": today, "now": now}).scalar()

    # 10. 收案移交（含卷宗审核字段）
    conn.execute(text("""
        INSERT INTO oa.case_intake_handover (lead_id, client_id, fee_agreement_id, case_id, handover_from_employee_id, handover_to_employee_id, handover_time, received_time, handover_status, material_check_result, missing_materials, material_list_json, archive_reviewer_id, archive_review_status, archive_review_time, archive_review_remark, supplement_requirement, remark, created_at, updated_at, status)
        VALUES (:lead_id, :client_id, :fee_agreement_id, :case_id, :emp_market, :emp_case_mgr, :yesterday, :now, 'received', 'complete', NULL, '[{"material": "身份证复印件", "has": true}, {"material": "事故认定书", "has": true}, {"material": "医疗票据", "has": true}]'::json,
                :emp_case_mgr, 2, :now, '材料齐全，符合收案标准', '无', '市场已当面确认当事人诉求和付费意愿。', :now, :now, 'active')
    """), {"lead_id": lead_id, "client_id": client_id, "fee_agreement_id": fee_agreement_id, "case_id": case_id,
           "emp_market": EMP_MARKET, "emp_case_mgr": EMP_CASE_MGR, "yesterday": yesterday, "now": now})

    # 11. 案件主体
    conn.execute(text("""
        INSERT INTO oa.case_party (case_id, party_role, party_type, id_card_or_credit_code, party_id, created_at, updated_at, status)
        VALUES (:case_id, 'client', 'individual', '320722199001011234', :party_id, :now, :now, 'active')
    """), {"case_id": case_id, "party_id": party_id, "now": now})

    # 12. 案件分配（主办、协办、实习律师，含案件组别）
    conn.execute(text("""
        INSERT INTO oa.case_assignment (case_id, assigned_role, employee_id, assigned_by, assigned_at, assignment_reason, work_scope, case_group, created_at, updated_at, status)
        VALUES (:case_id, 'main_lawyer', :emp_lawyer_main, :emp_case_mgr, :now, '擅长交通事故案件', '负责案件整体策略、出庭、与对方及保险公司谈判。', 2, :now, :now, 'active')
    """), {"case_id": case_id, "emp_lawyer_main": EMP_LAWYER_MAIN, "emp_case_mgr": EMP_CASE_MGR, "now": now})
    conn.execute(text("""
        INSERT INTO oa.case_assignment (case_id, assigned_role, employee_id, assigned_by, assigned_at, assignment_reason, work_scope, case_group, created_at, updated_at, status)
        VALUES (:case_id, 'co_lawyer', :emp_lawyer_assist, :emp_case_mgr, :now, '协助主办律师', '负责证据整理、法律文书起草、客户沟通。', 2, :now, :now, 'active')
    """), {"case_id": case_id, "emp_lawyer_assist": emp_lawyer_assist, "emp_case_mgr": EMP_CASE_MGR, "now": now})
    conn.execute(text("""
        INSERT INTO oa.case_assignment (case_id, assigned_role, employee_id, assigned_by, assigned_at, assignment_reason, work_scope, case_group, created_at, updated_at, status)
        VALUES (:case_id, 'trainee', :emp_trainee, :emp_case_mgr, :now, '跟案学习', '负责案件材料归档、庭审记录、法规检索。', 2, :now, :now, 'active')
    """), {"case_id": case_id, "emp_trainee": emp_trainee, "emp_case_mgr": EMP_CASE_MGR, "now": now})

    # 13. 案件状态流转（含办理节点）
    conn.execute(text("""
        INSERT INTO oa.case_status_log (case_id, from_stage, to_stage, from_status, to_status, progress_summary, internal_note, work_node, changed_by, changed_at, customer_visible, created_at, updated_at, status)
        VALUES (:case_id, NULL, 'intake', NULL, 'intake', '案件已收案，完成利益冲突审查。', '对方当事人为王某某及某保险公司，无利益冲突。', '收案建档', :emp_case_mgr, :now, false, :now, :now, 'active')
    """), {"case_id": case_id, "emp_case_mgr": EMP_CASE_MGR, "now": now})
    conn.execute(text("""
        INSERT INTO oa.case_status_log (case_id, from_stage, to_stage, from_status, to_status, progress_summary, internal_note, work_node, changed_by, changed_at, customer_visible, created_at, updated_at, status)
        VALUES (:case_id, 'intake', 'material', 'intake', 'material_preparation', '案件已分配给主办律师，开始整理证据材料。', '需要调取事故认定书、医院病历、工资流水。', '整理材料', :emp_case_mgr, :now, false, :now, :now, 'active')
    """), {"case_id": case_id, "emp_case_mgr": EMP_CASE_MGR, "now": now})
    conn.execute(text("""
        INSERT INTO oa.case_status_log (case_id, from_stage, to_stage, from_status, to_status, progress_summary, internal_note, work_node, changed_by, changed_at, customer_visible, created_at, updated_at, status)
        VALUES (:case_id, 'material', 'filing', 'material_preparation', 'filing_review', '材料齐全，准备向法院提交立案。', '已生成起诉状初稿，等待当事人签字确认。', '立案审核中', :emp_lawyer_main, :now, false, :now, :now, 'active')
    """), {"case_id": case_id, "emp_lawyer_main": EMP_LAWYER_MAIN, "now": now})

    # 14. 付款计划（新增 payment_node 字段）
    pp_first = conn.execute(text("""
        INSERT INTO oa.fin_payment_plan (payment_plan_no, fee_agreement_id, case_id, plan_name, payment_node, receivable_amount, due_date, received_amount, last_follow_time, payment_node_status, market_responsible_id, case_manager_responsible_id, created_at, updated_at, status)
        VALUES ('PP20260709001', :fee_agreement_id, :case_id, '签约首付款', 'sign_first', 20000.00, :today, 20000.00, :now, 2, :emp_market, :emp_case_mgr, :now, :now, 'active')
        RETURNING id
    """), {"fee_agreement_id": fee_agreement_id, "case_id": case_id, "emp_market": EMP_MARKET, "emp_case_mgr": EMP_CASE_MGR, "today": today, "now": now}).scalar()
    pp_balance = conn.execute(text("""
        INSERT INTO oa.fin_payment_plan (payment_plan_no, fee_agreement_id, case_id, plan_name, payment_node, receivable_amount, due_date, received_amount, payment_node_status, market_responsible_id, case_manager_responsible_id, created_at, updated_at, status)
        VALUES ('PP20260709002', :fee_agreement_id, :case_id, '回款尾款（风险代理）', 'risk_balance', 180000.00, :next_week, 0.00, 0, :emp_market, :emp_case_mgr, :now, :now, 'active')
        RETURNING id
    """), {"fee_agreement_id": fee_agreement_id, "case_id": case_id, "emp_market": EMP_MARKET, "emp_case_mgr": EMP_CASE_MGR, "next_week": next_week, "now": now}).scalar()

    # 15. 回款记录
    conn.execute(text("""
        INSERT INTO oa.fin_payment_record (payment_plan_id, case_id, client_id, received_amount, received_at, payment_method, payer_name, bank_flow_no, confirm_status, remark, created_at, updated_at, status)
        VALUES (:pp_first, :case_id, :client_id, 20000.00, :now, 'bank_transfer', '李四', 'BF20260709001', 'confirmed', '签约首付款已到账', :now, :now, 'active')
    """), {"pp_first": pp_first, "case_id": case_id, "client_id": client_id, "now": now})

    # 16. 发票
    conn.execute(text("""
        INSERT INTO oa.fin_invoice (invoice_no, case_id, client_id, invoice_amount, invoice_type, invoice_status, issued_at, invoice_title, tax_no, created_at, updated_at, status)
        VALUES ('I20260709001', :case_id, :client_id, 20000.00, 'service', 'issued', :now, '李四', '320722199001011234', :now, :now, 'active')
    """), {"case_id": case_id, "client_id": client_id, "now": now})

    # 17. 调档任务
    conn.execute(text("""
        INSERT INTO oa.case_retrieval_task (case_id, task_no, target_unit_type, target_unit_name, retrieval_matter, retrieval_reason, required_materials, assigned_lawyer_id, assigned_by, assigned_at, deadline_at, task_status, review_status, created_at, updated_at, status)
        VALUES (:case_id, 'RD20260709001', '交警大队', '连云港市公安局交警支队海州大队', '调取道路交通事故认定书原件及对方车辆保险信息。', '立案必备材料', '委托书、介绍信、律师证复印件', :emp_lawyer_main, :emp_case_mgr, :now, :next_week, 'in_progress', 'pending', :now, :now, 'active')
    """), {"case_id": case_id, "emp_lawyer_main": EMP_LAWYER_MAIN, "emp_case_mgr": EMP_CASE_MGR, "next_week": next_week, "now": now})

    # 18. 律师工作日志
    conn.execute(text("""
        INSERT INTO oa.legal_work_log (case_id, employee_id, work_date, work_type, work_content, work_hours, customer_visible, created_at, updated_at, status)
        VALUES (:case_id, :emp_lawyer_main, :today, 'client_meeting', '与李四面谈，确认诉讼请求和赔偿清单，签署委托合同及授权委托书。', 2.5, true, :now, :now, 'active')
    """), {"case_id": case_id, "emp_lawyer_main": EMP_LAWYER_MAIN, "today": today, "now": now})

    # 19. 办案期限
    conn.execute(text("""
        INSERT INTO oa.legal_deadline (case_id, deadline_title, deadline_type, deadline_time, responsible_employee_id, remind_channel, deadline_status, created_at, updated_at, status)
        VALUES (:case_id, '向法院提交立案材料', 'filing', :tomorrow, :emp_lawyer_main, 'app', 'not_started', :now, :now, 'active')
    """), {"case_id": case_id, "emp_lawyer_main": EMP_LAWYER_MAIN, "tomorrow": tomorrow, "now": now})

    # 20. 庭审/会议（新增 clerk 字段）
    conn.execute(text("""
        INSERT INTO oa.court_hearing (case_id, event_type, event_time, location, courtroom, judge_or_host, clerk, result_status, created_at, updated_at, status)
        VALUES (:case_id, 'pretrial', :next_week, '海州区人民法院', '第三法庭', '待定', '待定', 'scheduled', :now, :now, 'active')
    """), {"case_id": case_id, "next_week": next_week, "now": now})

    # 21. 证据目录
    conn.execute(text("""
        INSERT INTO oa.evidence_item (case_id, evidence_no, evidence_name, evidence_type, proof_purpose, source_from, original_or_copy, review_status, sort_order, created_at, updated_at, status)
        VALUES (:case_id, 'E20260709001', '道路交通事故认定书', 'official_document', '证明事故责任划分', '交警大队', 'copy', 'pending', 1, :now, :now, 'active')
    """), {"case_id": case_id, "now": now})

    print(f"真实数据插入完成：")
    print(f"  当事人 party_id={party_id}")
    print(f"  客户 client_id={client_id}")
    print(f"  线索 lead_id={lead_id}")
    print(f"  案件 case_id={case_id}")
    print(f"  收费协议 fee_agreement_id={fee_agreement_id}")
    print(f"  协办律师 emp_lawyer_assist={emp_lawyer_assist}")
    print(f"  实习律师 emp_trainee={emp_trainee}")
