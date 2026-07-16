"""
案件管理部整体流程测试数据。
场景：钱七离婚财产分割案，从利益冲突审查、收案移交、案件分配、
      材料准备、立案、开庭、调解到结案的完整案件管理流程。
"""
from datetime import datetime, date, timezone, timedelta
from sqlalchemy import create_engine, text
from app.core.config import settings

engine = create_engine(settings.database_url_with_search_path, future=True)

now = datetime.now(timezone.utc)
today = date.today()
yesterday = today - timedelta(days=1)
tomorrow = today + timedelta(days=1)
next_week = today + timedelta(days=7)
two_weeks = today + timedelta(days=14)

# 员工 ID
EMP_WANGWU = 3      # 案件管理部 王五
EMP_ZHAOLIU = 4     # 律师部 赵六（主办）
EMP_SUNQI = 5       # 律师部 孙七（协办）
EMP_ZHOUBA = 6      # 律师部 周八（实习）
DEPT_CASE = 2       # 案件管理部
DEPT_LAWYER = 3     # 律师部

# 本脚本生成的业务主键（用于幂等清理）
PARTY_CODE = 'P20260709005'
CLIENT_NO = 'C20260709005'
LEAD_NO = 'L20260709005'
CASE_NO = 'C20260709002'
AGREEMENT_NO = 'A20260709002'


def cleanup_previous_test_data(conn) -> None:
    """按业务主键清理上一轮测试数据（按外键依赖反向删除）。"""
    case_id = conn.execute(
        text("SELECT id FROM oa.case_main WHERE case_no = :no"),
        {"no": CASE_NO},
    ).scalar()

    if case_id:
        # 新表（即使当前脚本未写入，也清理以防后续扩展）
        conn.execute(text("DELETE FROM oa.case_close_review WHERE case_id = :case_id"), {"case_id": case_id})
        conn.execute(text("DELETE FROM oa.case_file_handover WHERE case_id = :case_id"), {"case_id": case_id})
        conn.execute(text("DELETE FROM oa.case_assignment_history WHERE case_id = :case_id"), {"case_id": case_id})
        conn.execute(text("DELETE FROM oa.case_intake_review WHERE case_id = :case_id"), {"case_id": case_id})
        # 财务/案件子表
        conn.execute(text("DELETE FROM oa.fin_refund_record WHERE case_id = :case_id"), {"case_id": case_id})
        conn.execute(text("DELETE FROM oa.fin_payment_followup WHERE case_id = :case_id"), {"case_id": case_id})
        conn.execute(text("DELETE FROM oa.fin_invoice WHERE case_id = :case_id"), {"case_id": case_id})
        conn.execute(text("DELETE FROM oa.fin_payment_record WHERE case_id = :case_id"), {"case_id": case_id})
        conn.execute(text("DELETE FROM oa.fin_payment_plan WHERE case_id = :case_id"), {"case_id": case_id})
        # 律师/调档子表
        conn.execute(text("DELETE FROM oa.evidence_item WHERE case_id = :case_id"), {"case_id": case_id})
        conn.execute(text("""
            DELETE FROM oa.court_hearing_attendee
            WHERE hearing_id IN (SELECT id FROM oa.court_hearing WHERE case_id = :case_id)
        """), {"case_id": case_id})
        conn.execute(text("DELETE FROM oa.court_hearing WHERE case_id = :case_id"), {"case_id": case_id})
        conn.execute(text("DELETE FROM oa.legal_document WHERE case_id = :case_id"), {"case_id": case_id})
        conn.execute(text("DELETE FROM oa.legal_deadline WHERE case_id = :case_id"), {"case_id": case_id})
        conn.execute(text("DELETE FROM oa.legal_work_log WHERE case_id = :case_id"), {"case_id": case_id})
        conn.execute(text("DELETE FROM oa.case_retrieval_task_log WHERE case_id = :case_id"), {"case_id": case_id})
        conn.execute(text("DELETE FROM oa.case_retrieval_task WHERE case_id = :case_id"), {"case_id": case_id})
        # 案件子表
        conn.execute(text("DELETE FROM oa.case_status_log WHERE case_id = :case_id"), {"case_id": case_id})
        conn.execute(text("DELETE FROM oa.case_assignment WHERE case_id = :case_id"), {"case_id": case_id})
        conn.execute(text("DELETE FROM oa.case_material WHERE case_id = :case_id"), {"case_id": case_id})
        conn.execute(text("DELETE FROM oa.case_party WHERE case_id = :case_id"), {"case_id": case_id})
        conn.execute(text("DELETE FROM oa.case_conflict_check WHERE case_id = :case_id"), {"case_id": case_id})
        conn.execute(text("DELETE FROM oa.case_intake_handover WHERE case_id = :case_id"), {"case_id": case_id})
        # 收费协议与案件主表
        conn.execute(text("DELETE FROM oa.fin_fee_agreement WHERE case_id = :case_id"), {"case_id": case_id})
        conn.execute(text("DELETE FROM oa.case_main WHERE id = :case_id"), {"case_id": case_id})

    lead_id = conn.execute(
        text("SELECT id FROM oa.crm_lead WHERE lead_no = :no"),
        {"no": LEAD_NO},
    ).scalar()
    if lead_id:
        conn.execute(text("DELETE FROM oa.crm_lead WHERE id = :lead_id"), {"lead_id": lead_id})

    client_id = conn.execute(
        text("SELECT id FROM oa.crm_client WHERE client_no = :no"),
        {"no": CLIENT_NO},
    ).scalar()
    if client_id:
        conn.execute(text("DELETE FROM oa.crm_client WHERE id = :client_id"), {"client_id": client_id})

    party_id = conn.execute(
        text("SELECT id FROM oa.party_main WHERE party_code = :code"),
        {"code": PARTY_CODE},
    ).scalar()
    if party_id:
        conn.execute(text("DELETE FROM oa.party_main WHERE id = :party_id"), {"party_id": party_id})

    print("[case_management_flow_test] Cleaned existing test data")


with engine.begin() as conn:
    cleanup_previous_test_data(conn)

    # ============================================================
    # 1. 当事人 / 客户 / 线索
    # ============================================================
    party_id = conn.execute(text("""
        INSERT INTO oa.party_main (
            party_code, party_type, party_name, gender, mobile, id_type, id_number,
            address, is_repeat_party, party_status, is_deleted, created_at, updated_at
        ) VALUES (
            'P20260709005', 1, '钱七', 2, '13955556666', 1, '320722198001011234',
            '江苏省连云港市海州区', 0, 1, 0, :now, :now
        )
        RETURNING id
    """), {"now": now}).scalar()

    client_id = conn.execute(text("""
        INSERT INTO oa.crm_client (
            client_no, client_type, id_card_no, client_level, risk_level, privacy_level,
            profile_summary, owner_employee_id, case_source, status, created_at, updated_at
        ) VALUES (
            'C20260709005', 'individual', '320722198001011234', 'vip', 'medium', 'high',
            '钱七（离婚财产分割案件当事人）', :emp_id, 10, 'active', :now, :now
        )
        RETURNING id
    """), {"emp_id": EMP_WANGWU, "now": now}).scalar()

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
            'L20260709005', '钱七离婚财产分割咨询',
            '当事人发现配偶隐匿夫妻共同财产，拟起诉离婚并主张财产分割。',
            '希望委托律师处理离婚诉讼，查明对方隐匿财产并争取合理分割。',
            'high', 'converted',
            10, '老客户转介绍', :emp_id, :dept,
            :emp_id, NULL, :emp_id,
            1, 4, 50000.00, 5000.00, 45000.00, :next_week,
            1, :yesterday, :emp_id,
            1, '涉及财产隐匿，案情复杂', 0, :yesterday, :yesterday,
            :now, :now, 'active'
        )
        RETURNING id
    """), {"emp_id": EMP_WANGWU, "dept": DEPT_CASE, "next_week": next_week, "yesterday": yesterday, "now": now}).scalar()

    # ============================================================
    # 2. 案件主表
    # ============================================================
    case_id = conn.execute(text("""
        INSERT INTO oa.case_main (
            case_no, case_title, client_id, case_stage, case_status, court_or_agency,
            accept_date, filing_date, close_date, case_brief, claim_summary,
            main_lawyer_id, case_manager_id, conflict_check_status, important_level,
            case_type, created_at, updated_at, status, remark
        ) VALUES (
            'C20260709002', '钱七诉其配偶离婚财产分割纠纷案', :client_id, 'intake', 'accepted',
            '连云港市海州区人民法院', :today, :tomorrow, NULL,
            '钱七离婚财产分割案件，涉及房产、车辆、银行存款等共同财产。',
            '请求法院判决离婚并依法分割夫妻共同财产，查明对方隐匿财产。',
            :main_lawyer, :case_manager, 'passed', 'important',
            1, :now, :now, 'active', '案件管理部测试案件'
        )
        RETURNING id
    """), {"client_id": client_id, "main_lawyer": EMP_ZHAOLIU, "case_manager": EMP_WANGWU,
           "today": today, "tomorrow": tomorrow, "now": now}).scalar()

    # ============================================================
    # 3. 利益冲突审查
    # ============================================================
    conn.execute(text("""
        INSERT INTO oa.case_conflict_check (
            case_id, client_id, checked_by, checked_at, check_scope, conflict_target,
            conflict_summary, check_stage, check_department_id, status, remark,
            lead_id, party_id, created_at, created_by, updated_at, updated_by
        ) VALUES (
            :case_id, :client_id, :emp_id, :now, '全所利益冲突',
            '对方当事人：钱七配偶；关联律所：无',
            '经核查，本所及本所律师与案件相对方不存在利益冲突，可以受理。',
            1, :dept, 'passed', '审查通过',
            :lead_id, :party_id, :now, :emp_id, :now, :emp_id
        )
    """), {"case_id": case_id, "client_id": client_id, "emp_id": EMP_WANGWU, "dept": DEPT_CASE,
           "lead_id": lead_id, "party_id": party_id, "now": now})

    # ============================================================
    # 4. 收案移交
    # ============================================================
    fee_agreement_id = conn.execute(text("""
        INSERT INTO oa.fin_fee_agreement (
            agreement_no, case_id, client_id, contract_no, fee_type, agreement_amount,
            currency, sign_date, payment_terms, responsible_employee_id, agreement_status,
            created_at, updated_at, status, remark
        ) VALUES (
            'A20260709002', :case_id, :client_id, 'HT20260709002', 'fixed', 50000.00,
            'CNY', :today, '签约支付5000元；立案后支付15000元；判决生效后支付30000元。', :main_lawyer, 'signed',
            :now, :now, 'active', '固定收费'
        )
        RETURNING id
    """), {"case_id": case_id, "client_id": client_id, "main_lawyer": EMP_ZHAOLIU,
           "today": today, "now": now}).scalar()

    material_list = '[{"material":"身份证","has":true},{"material":"结婚证","has":true},{"material":"财产线索","has":true}]'

    conn.execute(text("""
        INSERT INTO oa.case_intake_handover (
            lead_id, client_id, fee_agreement_id, case_id, handover_from_employee_id,
            handover_to_employee_id, handover_time, received_time, handover_status,
            material_check_result, missing_materials, material_list_json, archive_reviewer_id,
            archive_review_status, archive_review_time, archive_review_remark,
            supplement_requirement, remark, created_at, updated_at, status
        ) VALUES (
            :lead_id, :client_id, :fee_agreement_id, :case_id, :emp_id,
            :case_manager, :yesterday, :now, 'received',
            'complete', NULL, :material_list, :case_manager, '2', :now, '材料齐全，符合收案标准',
            '无', '市场转交，已签署委托合同', :now, :now, 'active'
        )
    """), {"lead_id": lead_id, "client_id": client_id, "fee_agreement_id": fee_agreement_id,
           "case_id": case_id, "emp_id": EMP_WANGWU, "case_manager": EMP_WANGWU,
           "material_list": material_list, "yesterday": yesterday, "now": now})

    # ============================================================
    # 5. 案件主体
    # ============================================================
    conn.execute(text("""
        INSERT INTO oa.case_party (
            case_id, party_role, party_type, id_card_or_credit_code, party_id,
            created_at, updated_at, status
        ) VALUES (
            :case_id, 'client', 'individual', '320722198001011234', :party_id,
            :now, :now, 'active'
        )
    """), {"case_id": case_id, "party_id": party_id, "now": now})

    # ============================================================
    # 6. 案件分配
    # ============================================================
    assignments = [
        ('main_lawyer', EMP_ZHAOLIU, '主办律师', '负责案件整体策略、出庭、与对方谈判。'),
        ('co_lawyer', EMP_SUNQI, '协办律师', '负责证据整理、财产调查、法律文书起草。'),
        ('trainee', EMP_ZHOUBA, '实习律师', '负责案件材料归档、庭审记录、法规检索。'),
    ]
    for role, emp_id, role_name, scope in assignments:
        conn.execute(text("""
            INSERT INTO oa.case_assignment (
                case_id, assigned_role, employee_id, assigned_by, assigned_at,
                assignment_reason, work_scope, case_group, created_at, updated_at, status
            ) VALUES (
                :case_id, :role, :emp_id, :assigned_by, :now,
                :reason, :scope, '1', :now, :now, 'active'
            )
        """), {"case_id": case_id, "role": role, "emp_id": emp_id,
               "assigned_by": EMP_WANGWU, "reason": role_name, "scope": scope, "now": now})

    # ============================================================
    # 7. 付款计划
    # ============================================================
    pp_sign = conn.execute(text("""
        INSERT INTO oa.fin_payment_plan (
            payment_plan_no, fee_agreement_id, case_id, plan_name, receivable_amount,
            due_date, received_amount, last_follow_time, payment_node_status,
            market_responsible_id, case_manager_responsible_id, created_at, updated_at, status
        ) VALUES (
            'PP20260709003', :fee_agreement_id, :case_id, '签约首付款', 5000.00,
            :today, 5000.00, :now, 2,
            :emp_id, :case_manager, :now, :now, 'active'
        )
        RETURNING id
    """), {"fee_agreement_id": fee_agreement_id, "case_id": case_id, "emp_id": EMP_WANGWU,
           "case_manager": EMP_WANGWU, "today": today, "now": now}).scalar()

    pp_filing = conn.execute(text("""
        INSERT INTO oa.fin_payment_plan (
            payment_plan_no, fee_agreement_id, case_id, plan_name, receivable_amount,
            due_date, received_amount, payment_node_status,
            market_responsible_id, case_manager_responsible_id, created_at, updated_at, status
        ) VALUES (
            'PP20260709004', :fee_agreement_id, :case_id, '立案阶段款', 15000.00,
            :next_week, 0.00, 0,
            :emp_id, :case_manager, :now, :now, 'active'
        )
        RETURNING id
    """), {"fee_agreement_id": fee_agreement_id, "case_id": case_id, "emp_id": EMP_WANGWU,
           "case_manager": EMP_WANGWU, "next_week": next_week, "now": now}).scalar()

    pp_final = conn.execute(text("""
        INSERT INTO oa.fin_payment_plan (
            payment_plan_no, fee_agreement_id, case_id, plan_name, receivable_amount,
            due_date, received_amount, payment_node_status,
            market_responsible_id, case_manager_responsible_id, created_at, updated_at, status
        ) VALUES (
            'PP20260709005', :fee_agreement_id, :case_id, '判决生效尾款', 30000.00,
            :two_weeks, 0.00, 0,
            :emp_id, :case_manager, :now, :now, 'active'
        )
        RETURNING id
    """), {"fee_agreement_id": fee_agreement_id, "case_id": case_id, "emp_id": EMP_WANGWU,
           "case_manager": EMP_WANGWU, "two_weeks": two_weeks, "now": now}).scalar()

    # ============================================================
    # 8. 案件状态流转
    # ============================================================
    status_flow = [
        (None, 'intake', None, 'accepted', '案件已收案，完成利益冲突审查和委托合同签署。', '收案建档'),
        ('intake', 'material', 'accepted', 'material_preparation', '已分配给主办律师，开始整理证据材料和财产线索。', '整理材料'),
        ('material', 'filing', 'material_preparation', 'filing_review', '材料齐全，已向法院提交立案申请。', '立案审核'),
        ('filing', 'trial', 'filing_review', 'trial_ready', '法院已受理，等待开庭审理。', '庭前准备'),
        ('trial', 'mediation', 'trial_ready', 'mediation', '庭审结束，双方进入法院调解程序。', '庭后调解'),
        ('mediation', 'closed', 'mediation', 'closed', '调解成功，案件已结案。', '结案归档'),
    ]
    for from_stage, to_stage, from_status, to_status, summary, node in status_flow:
        conn.execute(text("""
            INSERT INTO oa.case_status_log (
                case_id, from_stage, to_stage, from_status, to_status, progress_summary,
                internal_note, work_node, changed_by, changed_at, customer_visible,
                created_at, updated_at, status
            ) VALUES (
                :case_id, :from_stage, :to_stage, :from_status, :to_status, :summary,
                NULL, :node, :changed_by, :now, false,
                :now, :now, 'active'
            )
        """), {"case_id": case_id, "from_stage": from_stage, "to_stage": to_stage,
               "from_status": from_status, "to_status": to_status, "summary": summary,
               "node": node, "changed_by": EMP_WANGWU, "now": now})

    # ============================================================
    # 9. 案件材料
    # ============================================================
    materials = [
        ('身份证', 'identity', 'client'),
        ('结婚证', 'marriage_certificate', 'client'),
        ('房产证', 'property_certificate', 'client'),
        ('银行流水', 'bank_statement', 'client'),
        ('微信聊天记录', 'chat_record', 'client'),
    ]
    for name, mtype, source in materials:
        conn.execute(text("""
            INSERT INTO oa.case_material (
                case_id, material_name, material_type, source_from, received_at,
                received_by, review_status, created_at, updated_at, status
            ) VALUES (
                :case_id, :name, :mtype, :source, :now,
                :emp_id, 'approved', :now, :now, 'active'
            )
        """), {"case_id": case_id, "name": name, "mtype": mtype, "source": source,
               "emp_id": EMP_ZHAOLIU, "now": now})

    # ============================================================
    # 10. 调档任务及日志
    # ============================================================
    retrieval_id = conn.execute(text("""
        INSERT INTO oa.case_retrieval_task (
            case_id, task_no, target_unit_type, target_unit_name, retrieval_matter,
            retrieval_reason, required_materials, assigned_lawyer_id, assigned_by,
            assigned_at, deadline_at, task_status, review_status, created_at, updated_at, status
        ) VALUES (
            :case_id, 'RD20260709002', '不动产登记中心', '连云港市不动产登记中心', '查询对方名下房产登记信息。',
            '查明夫妻共同财产', '调查令、律师证复印件、授权委托书', :lawyer, :case_manager,
            :now, :next_week, 'completed', 'approved', :now, :now, 'active'
        )
        RETURNING id
    """), {"case_id": case_id, "lawyer": EMP_ZHAOLIU, "case_manager": EMP_WANGWU,
           "next_week": next_week, "now": now}).scalar()

    # 调档任务日志
    conn.execute(text("""
        INSERT INTO oa.case_retrieval_task_log (
            retrieval_task_id, case_id, action_type, old_status, new_status, content,
            remark, operator_id, operated_at, customer_visible, created_at, updated_at, status
        ) VALUES (
            :retrieval_id, :case_id, 'assign', NULL, 'in_progress', '案件管理部王五将调档任务分配给主办律师赵六。',
            '已准备调查令', :emp_id, :now, false, :now, :now, 'active'
        )
    """), {"retrieval_id": retrieval_id, "case_id": case_id, "emp_id": EMP_WANGWU, "now": now})

    conn.execute(text("""
        INSERT INTO oa.case_retrieval_task_log (
            retrieval_task_id, case_id, action_type, old_status, new_status, content,
            remark, operator_id, operated_at, customer_visible, created_at, updated_at, status
        ) VALUES (
            :retrieval_id, :case_id, 'complete', 'in_progress', 'completed', '赵六律师完成房产信息调取，查明对方名下另有2套房产。',
            '已归档至案件材料', :lawyer, :now, false, :now, :now, 'active'
        )
    """), {"retrieval_id": retrieval_id, "case_id": case_id, "lawyer": EMP_ZHAOLIU, "now": now})

    # ============================================================
    # 11. 律师工作日志
    # ============================================================
    work_logs = [
        (EMP_ZHAOLIU, 'client_meeting', '与钱七面谈，了解婚姻财产状况，制定诉讼策略。', 2.0),
        (EMP_SUNQI, 'evidence_collection', '整理银行流水、房产证、聊天记录等证据材料。', 3.5),
        (EMP_ZHAOLIU, 'court_filing', '前往法院提交立案材料并缴纳诉讼费。', 1.5),
        (EMP_ZHAOLIU, 'court_hearing', '参加庭审，发表代理意见，参与调解。', 4.0),
    ]
    for emp_id, wtype, content, hours in work_logs:
        conn.execute(text("""
            INSERT INTO oa.legal_work_log (
                case_id, employee_id, work_date, work_type, work_content, work_hours,
                result_summary, customer_visible, created_at, updated_at, status
            ) VALUES (
                :case_id, :emp_id, :today, :wtype, :content, :hours,
                '工作按计划完成', true, :now, :now, 'active'
            )
        """), {"case_id": case_id, "emp_id": emp_id, "today": today, "wtype": wtype,
               "content": content, "hours": hours, "now": now})

    # ============================================================
    # 12. 办案期限
    # ============================================================
    deadlines = [
        ('提交立案材料', 'filing', tomorrow, 'completed'),
        ('证据交换', 'evidence_exchange', next_week, 'not_started'),
        ('开庭', 'court_hearing', two_weeks, 'not_started'),
    ]
    for title, dtype, dt, dstatus in deadlines:
        conn.execute(text("""
            INSERT INTO oa.legal_deadline (
                case_id, deadline_title, deadline_type, deadline_time, responsible_employee_id,
                remind_channel, deadline_status, created_at, updated_at, status
            ) VALUES (
                :case_id, :title, :dtype, :dt, :lawyer,
                'app', :dstatus, :now, :now, 'active'
            )
        """), {"case_id": case_id, "title": title, "dtype": dtype, "dt": dt,
               "dstatus": dstatus, "lawyer": EMP_ZHAOLIU, "now": now})

    # ============================================================
    # 13. 法律文书
    # ============================================================
    documents = [
        ('民事起诉状', 'indictment', 'v1.0'),
        ('财产保全申请书', 'property_preservation', 'v1.0'),
        ('律师代理词', 'agency_opinion', 'v1.0'),
        ('调解协议', 'mediation_agreement', 'v1.0'),
    ]
    for title, dtype, version in documents:
        conn.execute(text("""
            INSERT INTO oa.legal_document (
                case_id, document_title, document_type, version_no, draft_employee_id,
                review_employee_id, document_status, submit_target, submitted_at,
                created_by, updated_at, updated_by, status, created_at
            ) VALUES (
                :case_id, :title, :dtype, :version, :draft,
                :review, 'approved', '法院', :now,
                :draft, :now, :review, 'active', :now
            )
        """), {"case_id": case_id, "title": title, "dtype": dtype, "version": version,
               "draft": EMP_ZHAOLIU, "review": EMP_SUNQI, "now": now})

    # ============================================================
    # 14. 庭审及参与人
    # ============================================================
    hearing_id = conn.execute(text("""
        INSERT INTO oa.court_hearing (
            case_id, event_type, event_time, location, courtroom, judge_or_host,
            hearing_summary, result_status, created_at, updated_at, status
        ) VALUES (
            :case_id, 'trial', :two_weeks, '海州区人民法院', '第五法庭', '张法官',
            '庭审中双方就财产分割方案进行辩论，法官组织调解。', 'mediation_success',
            :now, :now, 'active'
        )
        RETURNING id
    """), {"case_id": case_id, "two_weeks": two_weeks, "now": now}).scalar()

    attendees = [
        (EMP_ZHAOLIU, 'main_lawyer', 'attended'),
        (EMP_SUNQI, 'co_lawyer', 'attended'),
        (EMP_ZHOUBA, 'trainee', 'attended'),
    ]
    for emp_id, role, status in attendees:
        conn.execute(text("""
            INSERT INTO oa.court_hearing_attendee (
                hearing_id, employee_id, attendee_role, attendance_status,
                created_at, updated_at, status
            ) VALUES (
                :hearing_id, :emp_id, :role, :status,
                :now, :now, 'active'
            )
        """), {"hearing_id": hearing_id, "emp_id": emp_id, "role": role, "status": status, "now": now})

    # ============================================================
    # 15. 证据目录
    # ============================================================
    evidence_items = [
        ('E20260709002', '结婚证', 'official_document', '证明婚姻关系', 1),
        ('E20260709003', '房产证', 'official_document', '证明夫妻共同房产', 2),
        ('E20260709004', '银行流水', 'financial_document', '证明夫妻共同财产及对方转移资金', 3),
        ('E20260709005', '微信聊天记录', 'chat_record', '证明对方承认隐匿财产', 4),
    ]
    for no, name, etype, purpose, order in evidence_items:
        conn.execute(text("""
            INSERT INTO oa.evidence_item (
                case_id, evidence_no, evidence_name, evidence_type, proof_purpose,
                source_from, original_or_copy, review_status, sort_order,
                created_at, updated_at, status
            ) VALUES (
                :case_id, :no, :name, :etype, :purpose,
                '当事人提供', 'original', 'approved', :order,
                :now, :now, 'active'
            )
        """), {"case_id": case_id, "no": no, "name": name, "etype": etype,
               "purpose": purpose, "order": order, "now": now})

    # ============================================================
    # 16. 回款记录
    # ============================================================
    conn.execute(text("""
        INSERT INTO oa.fin_payment_record (
            payment_plan_id, case_id, client_id, received_amount, received_at,
            payment_method, payer_name, bank_flow_no, confirm_status,
            remark, created_at, updated_at, status
        ) VALUES (
            :pp_id, :case_id, :client_id, 5000.00, :now,
            'bank_transfer', '钱七', 'BF20260709002', 'confirmed',
            '签约首付款已到账', :now, :now, 'active'
        )
    """), {"pp_id": pp_sign, "case_id": case_id, "client_id": client_id, "now": now})

    # ============================================================
    # 17. 发票
    # ============================================================
    conn.execute(text("""
        INSERT INTO oa.fin_invoice (
            invoice_no, case_id, client_id, invoice_amount, invoice_type,
            invoice_status, issued_at, invoice_title, tax_no,
            created_at, updated_at, status
        ) VALUES (
            'I20260709002', :case_id, :client_id, 5000.00, 'service',
            'issued', :now, '钱七', '320722198001011234',
            :now, :now, 'active'
        )
    """), {"case_id": case_id, "client_id": client_id, "now": now})

    # ============================================================
    # 18. 付款跟进
    # ============================================================
    conn.execute(text("""
        INSERT INTO oa.fin_payment_followup (
            payment_plan_id, fee_agreement_id, case_id, client_id, followup_employee_id,
            followup_department_id, followup_time, followup_method, followup_content,
            customer_feedback, followup_result, next_followup_time, is_overdue,
            created_at, created_by, updated_at, updated_by, status
        ) VALUES (
            :pp_id, :fee_id, :case_id, :client_id, :emp_id,
            :dept, :now, 'phone', '提醒客户按合同约定支付立案阶段款。',
            '客户表示本周内安排付款', 'pending', :next_week, false,
            :now, :emp_id, :now, :emp_id, 'active'
        )
    """), {"pp_id": pp_filing, "fee_id": fee_agreement_id, "case_id": case_id,
           "client_id": client_id, "emp_id": EMP_WANGWU, "dept": DEPT_CASE,
           "next_week": next_week, "now": now})

    # ============================================================
    # 19. 退款记录（模拟部分退款场景）
    # ============================================================
    conn.execute(text("""
        INSERT INTO oa.fin_refund_record (
            case_id, fee_agreement_id, refund_amount, refund_reason_type,
            refund_reason_detail, refund_date, refund_status,
            created_by, created_at, updated_at, updated_by, remark
        ) VALUES (
            :case_id, :fee_id, 1000.00, 1,
            '因案件调解结案，按约定退还部分前期费用。', :today, 2,
            :emp_id, :now, :now, :emp_id, '已审批通过'
        )
    """), {"case_id": case_id, "fee_id": fee_agreement_id, "today": today,
           "emp_id": EMP_WANGWU, "now": now})

    print("案件管理部整体流程测试数据插入完成：")
    print(f"  当事人 party_id={party_id}")
    print(f"  客户 client_id={client_id}")
    print(f"  线索 lead_id={lead_id}")
    print(f"  案件 case_id={case_id}")
    print(f"  收费协议 fee_agreement_id={fee_agreement_id}")
    print(f"  调档任务 retrieval_id={retrieval_id}")
    print(f"  庭审 hearing_id={hearing_id}")
