"""
律师部整体流程测试数据。
场景：复用钱七离婚财产分割案（case_id=9），验证主办律师、协办律师、实习律师
      在案件办理过程中的协作、文书审批、庭审准备等完整流程。
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
three_weeks = today + timedelta(days=21)

# 固定业务 ID（基于钱七案现有数据）
CASE_ID = 9
CLIENT_ID = 27
PARTY_ID = 25
FEE_AGREEMENT_ID = 9

# 员工 ID
EMP_ZHAOLIU = 4      # 主办律师 赵六
EMP_SUNQI = 5        # 协办律师 孙七
EMP_ZHOUBA = 6       # 实习律师 周八
EMP_WANGWU = 3       # 案件管理部 王五

DEPT_LAWYER = 3      # 律师部


def cleanup_lawyer_data(conn):
    """清理 case_id=9 上律师部相关的旧测试数据，保证脚本可重复运行。"""
    # 先清理有外键依赖的子表
    conn.execute(text("""
        DELETE FROM oa.court_hearing_attendee
        WHERE hearing_id IN (SELECT id FROM oa.court_hearing WHERE case_id = :case_id)
    """), {"case_id": CASE_ID})

    conn.execute(text("""
        DELETE FROM oa.case_retrieval_task_log
        WHERE retrieval_task_id IN (SELECT id FROM oa.case_retrieval_task WHERE case_id = :case_id)
    """), {"case_id": CASE_ID})

    # 再清理直接关联 case_id 的表
    for table in [
        "court_hearing",
        "evidence_item",
        "legal_work_log",
        "legal_document",
        "legal_deadline",
        "case_retrieval_task",
        "case_material",
        "case_status_log",
    ]:
        conn.execute(text(f"DELETE FROM oa.{table} WHERE case_id = :case_id"), {"case_id": CASE_ID})

    # 重置案件主表状态，保留收案结果
    conn.execute(text("""
        UPDATE oa.case_main
        SET case_stage = 'intake', case_status = 'accepted', updated_at = :now, updated_by = :emp_id
        WHERE id = :case_id
    """), {"case_id": CASE_ID, "now": now, "emp_id": EMP_WANGWU})


with engine.begin() as conn:
    # ============================================================
    # 0. 清理旧数据，重置案件状态
    # ============================================================
    cleanup_lawyer_data(conn)

    # ============================================================
    # 1. 案件材料（律师办案过程中收集、整理的材料）
    # ============================================================
    materials = [
        ('身份证', 'identity', 'client'),
        ('结婚证', 'marriage_certificate', 'client'),
        ('房产证', 'property_certificate', 'client'),
        ('银行流水', 'bank_statement', 'client'),
        ('微信聊天记录', 'chat_record', 'client'),
        ('对方隐匿财产线索', 'property_clue', 'investigation'),
    ]
    material_ids = {}
    for idx, (name, mtype, source) in enumerate(materials, 1):
        material_id = conn.execute(text("""
            INSERT INTO oa.case_material (
                case_id, material_name, material_type, source_from, received_at,
                received_by, review_status, created_at, updated_at, status
            ) VALUES (
                :case_id, :name, :mtype, :source, :now,
                :emp_id, 'approved', :now, :now, 'active'
            )
            RETURNING id
        """), {"case_id": CASE_ID, "name": name, "mtype": mtype, "source": source,
               "emp_id": EMP_ZHAOLIU, "now": now}).scalar()
        material_ids[name] = material_id

    # ============================================================
    # 2. 调档任务及日志
    # ============================================================
    retrieval_id = conn.execute(text("""
        INSERT INTO oa.case_retrieval_task (
            case_id, task_no, target_unit_type, target_unit_name, retrieval_matter,
            retrieval_reason, required_materials, assigned_lawyer_id, assigned_by,
            assigned_at, deadline_at, task_status, review_status, created_at, updated_at, status
        ) VALUES (
            :case_id, 'RD20260709003', '不动产登记中心', '连云港市不动产登记中心',
            '查询对方名下房产登记信息。', '查明夫妻共同财产',
            '调查令、律师证复印件、授权委托书', :lawyer, :case_manager,
            :now, :next_week, 'completed', 'approved', :now, :now, 'active'
        )
        RETURNING id
    """), {"case_id": CASE_ID, "lawyer": EMP_ZHAOLIU, "case_manager": EMP_WANGWU,
           "next_week": next_week, "now": now}).scalar()

    conn.execute(text("""
        INSERT INTO oa.case_retrieval_task_log (
            retrieval_task_id, case_id, action_type, old_status, new_status, content,
            remark, operator_id, operated_at, customer_visible, created_at, updated_at, status
        ) VALUES (
            :retrieval_id, :case_id, 'assign', NULL, 'in_progress',
            '案件管理部王五将调档任务分配给主办律师赵六。', '已准备调查令',
            :emp_id, :now, false, :now, :now, 'active'
        )
    """), {"retrieval_id": retrieval_id, "case_id": CASE_ID, "emp_id": EMP_WANGWU, "now": now})

    conn.execute(text("""
        INSERT INTO oa.case_retrieval_task_log (
            retrieval_task_id, case_id, action_type, old_status, new_status, content,
            remark, operator_id, operated_at, customer_visible, created_at, updated_at, status
        ) VALUES (
            :retrieval_id, :case_id, 'complete', 'in_progress', 'completed',
            '赵六律师完成房产信息调取，查明对方名下另有2套房产。', '已归档至案件材料',
            :lawyer, :now, false, :now, :now, 'active'
        )
    """), {"retrieval_id": retrieval_id, "case_id": CASE_ID, "lawyer": EMP_ZHAOLIU, "now": now})

    # ============================================================
    # 3. 律师工作日志（覆盖三类律师协作）
    # ============================================================
    work_logs = [
        # 主办律师
        (EMP_ZHAOLIU, 'client_meeting', '与钱七面谈，了解婚姻财产状况，制定诉讼策略和财产保全方案。', 2.5),
        (EMP_ZHAOLIU, 'case_strategy', '分析财产线索，确定调查方向和诉讼请求。', 1.5),
        (EMP_ZHAOLIU, 'court_filing', '前往法院提交立案材料并缴纳诉讼费。', 2.0),
        (EMP_ZHAOLIU, 'court_hearing', '参加庭审，发表代理意见，参与法院调解。', 4.0),
        # 协办律师
        (EMP_SUNQI, 'evidence_collection', '整理银行流水、房产证、聊天记录等证据材料并制作证据目录。', 3.5),
        (EMP_SUNQI, 'document_draft', '起草民事起诉状、财产保全申请书和律师代理词。', 4.0),
        (EMP_SUNQI, 'client_communication', '就证据补充和诉讼风险与钱七电话沟通。', 1.0),
        # 实习律师
        (EMP_ZHOUBA, 'legal_research', '检索离婚财产分割相关法规和相似判例。', 2.0),
        (EMP_ZHOUBA, 'material_archive', '整理案件材料，制作卷宗目录并扫描归档。', 2.5),
        (EMP_ZHOUBA, 'hearing_note', '参加庭审并记录庭审笔录要点。', 3.0),
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
        """), {"case_id": CASE_ID, "emp_id": emp_id, "today": today, "wtype": wtype,
               "content": content, "hours": hours, "now": now})

    # ============================================================
    # 4. 办案期限
    # ============================================================
    deadlines = [
        ('提交立案材料', 'filing', tomorrow, 'completed', EMP_ZHAOLIU),
        ('申请财产保全', 'preservation', next_week, 'in_progress', EMP_ZHAOLIU),
        ('证据交换', 'evidence_exchange', two_weeks, 'not_started', EMP_SUNQI),
        ('开庭审理', 'court_hearing', two_weeks, 'not_started', EMP_ZHAOLIU),
        ('领取调解书', 'mediation', three_weeks, 'not_started', EMP_ZHAOLIU),
    ]
    for title, dtype, dt, dstatus, responsible in deadlines:
        conn.execute(text("""
            INSERT INTO oa.legal_deadline (
                case_id, deadline_title, deadline_type, deadline_time, responsible_employee_id,
                remind_channel, deadline_status, created_at, updated_at, status
            ) VALUES (
                :case_id, :title, :dtype, :dt, :responsible,
                'app', :dstatus, :now, :now, 'active'
            )
        """), {"case_id": CASE_ID, "title": title, "dtype": dtype, "dt": dt,
               "dstatus": dstatus, "responsible": responsible, "now": now})

    # ============================================================
    # 5. 法律文书（含起草、审核、提交审批流）
    # ============================================================
    documents = [
        ('民事起诉状', 'indictment', 'v1.0', 'submitted', EMP_ZHAOLIU, EMP_SUNQI),
        ('财产保全申请书', 'property_preservation', 'v1.0', 'submitted', EMP_SUNQI, EMP_ZHAOLIU),
        ('律师代理词', 'agency_opinion', 'v1.0', 'approved', EMP_SUNQI, EMP_ZHAOLIU),
        ('调解协议', 'mediation_agreement', 'v1.0', 'draft', EMP_ZHAOLIU, EMP_SUNQI),
    ]
    for title, dtype, version, doc_status, draft, review in documents:
        submitted_at = now if doc_status in ('submitted', 'approved') else None
        conn.execute(text("""
            INSERT INTO oa.legal_document (
                case_id, document_title, document_type, version_no, draft_employee_id,
                review_employee_id, document_status, submit_target, submitted_at,
                created_by, updated_at, updated_by, status, created_at
            ) VALUES (
                :case_id, :title, :dtype, :version, :draft,
                :review, :doc_status, '法院', :submitted_at,
                :draft, :now, :review, 'active', :now
            )
        """), {"case_id": CASE_ID, "title": title, "dtype": dtype, "version": version,
               "draft": draft, "review": review, "doc_status": doc_status,
               "submitted_at": submitted_at, "now": now})

    # ============================================================
    # 6. 庭审/会议及参与人
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
    """), {"case_id": CASE_ID, "two_weeks": two_weeks, "now": now}).scalar()

    # 庭前会议
    pretrial_id = conn.execute(text("""
        INSERT INTO oa.court_hearing (
            case_id, event_type, event_time, location, courtroom, judge_or_host,
            hearing_summary, result_status, created_at, updated_at, status
        ) VALUES (
            :case_id, 'pretrial', :next_week, '海州区人民法院', '调解室', '李调解员',
            '庭前证据交换和调解意向沟通。', 'scheduled',
            :now, :now, 'active'
        )
        RETURNING id
    """), {"case_id": CASE_ID, "next_week": next_week, "now": now}).scalar()

    attendees = [
        (hearing_id, EMP_ZHAOLIU, 'main_lawyer', 'attended'),
        (hearing_id, EMP_SUNQI, 'co_lawyer', 'attended'),
        (hearing_id, EMP_ZHOUBA, 'trainee', 'attended'),
        (pretrial_id, EMP_ZHAOLIU, 'main_lawyer', 'attended'),
        (pretrial_id, EMP_SUNQI, 'co_lawyer', 'attended'),
    ]
    for hearing, emp_id, role, status in attendees:
        conn.execute(text("""
            INSERT INTO oa.court_hearing_attendee (
                hearing_id, employee_id, attendee_role, attendance_status,
                created_at, updated_at, status
            ) VALUES (
                :hearing_id, :emp_id, :role, :status,
                :now, :now, 'active'
            )
        """), {"hearing_id": hearing, "emp_id": emp_id, "role": role, "status": status, "now": now})

    # ============================================================
    # 7. 证据目录
    # ============================================================
    evidence_items = [
        ('E20260709006', '结婚证', 'official_document', '证明婚姻关系', 1, 'original'),
        ('E20260709007', '房产证', 'official_document', '证明夫妻共同房产', 2, 'original'),
        ('E20260709008', '银行流水', 'financial_document', '证明夫妻共同财产及对方转移资金', 3, 'copy'),
        ('E20260709009', '微信聊天记录', 'chat_record', '证明对方承认隐匿财产', 4, 'original'),
        ('E20260709010', '不动产登记查询结果', 'official_document', '证明对方名下另有房产', 5, 'copy'),
    ]
    for no, name, etype, purpose, order, original in evidence_items:
        conn.execute(text("""
            INSERT INTO oa.evidence_item (
                case_id, evidence_no, evidence_name, evidence_type, proof_purpose,
                source_from, original_or_copy, review_status, sort_order,
                created_at, updated_at, status
            ) VALUES (
                :case_id, :no, :name, :etype, :purpose,
                '当事人提供', :original, 'approved', :order,
                :now, :now, 'active'
            )
        """), {"case_id": CASE_ID, "no": no, "name": name, "etype": etype,
               "purpose": purpose, "original": original, "order": order, "now": now})

    # ============================================================
    # 8. 案件状态流转（完整律师部视角）
    # ============================================================
    status_flow = [
        (None, 'intake', None, 'accepted', '案件已收案，完成利益冲突审查和委托合同签署。', '收案建档', EMP_WANGWU),
        ('intake', 'material', 'accepted', 'material_preparation', '案件已分配给主办律师，开始整理证据材料和财产线索。', '整理材料', EMP_ZHAOLIU),
        ('material', 'investigation', 'material_preparation', 'investigation', '主办律师制定策略，协办律师配合调查财产，实习律师完成法规检索。', '调查取证', EMP_ZHAOLIU),
        ('investigation', 'filing', 'investigation', 'filing_review', '材料齐全，已向法院提交立案申请并申请财产保全。', '立案审核', EMP_ZHAOLIU),
        ('filing', 'trial', 'filing_review', 'trial_ready', '法院已受理，完成庭前会议和证据交换。', '庭前准备', EMP_SUNQI),
        ('trial', 'mediation', 'trial_ready', 'mediation', '庭审结束，双方在法院主持下达成调解意向。', '庭后调解', EMP_ZHAOLIU),
        ('mediation', 'closed', 'mediation', 'closed', '调解成功，案件已结案归档。', '结案归档', EMP_ZHAOLIU),
    ]
    for from_stage, to_stage, from_status, to_status, summary, node, changed_by in status_flow:
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
        """), {"case_id": CASE_ID, "from_stage": from_stage, "to_stage": to_stage,
               "from_status": from_status, "to_status": to_status, "summary": summary,
               "node": node, "changed_by": changed_by, "now": now})

    # ============================================================
    # 9. 更新案件主表为结案状态
    # ============================================================
    conn.execute(text("""
        UPDATE oa.case_main
        SET case_stage = 'closed', case_status = 'closed', updated_at = :now, updated_by = :emp_id
        WHERE id = :case_id
    """), {"case_id": CASE_ID, "now": now, "emp_id": EMP_ZHAOLIU})

    print("律师部整体流程测试数据插入完成：")
    print(f"  案件 case_id={CASE_ID}")
    print(f"  当事人 party_id={PARTY_ID}")
    print(f"  客户 client_id={CLIENT_ID}")
    print(f"  收费协议 fee_agreement_id={FEE_AGREEMENT_ID}")
    print(f"  调档任务 retrieval_id={retrieval_id}")
    print(f"  庭审 hearing_id={hearing_id}")
    print(f"  庭前会议 pretrial_id={pretrial_id}")
