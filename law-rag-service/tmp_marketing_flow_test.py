"""
市场拓展部整体流程测试数据。
场景：抖音直播推广活动产生多条线索，经过投放、直播、线索分配、电话邀约、
      预约到访、谈案、跟进等完整市场流程处理。
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

# 市场拓展部员工
EMP_ZHANGSAN = 1  # 张三
EMP_LISI = 2      # 李四
DEPT_MARKET = 1   # 市场拓展部

# 线索来源常量
SOURCE_LIVE = 1       # 直播间
SOURCE_AD = 2         # 广告投放
SOURCE_OFFLINE = 10   # 线下拓展

with engine.begin() as conn:
    # ============================================================
    # 1. 广告投放计划（抖音本地推-交通事故赔偿专题）
    # ============================================================
    campaign_id = conn.execute(text("""
        INSERT INTO oa.ops_ad_campaign (
            campaign_no, campaign_name, platform, case_source, campaign_type,
            start_date, end_date, budget_amount, owner_employee_id, campaign_status,
            remark, created_at, updated_at, status
        ) VALUES (
            'C20260709002', '抖音本地推-交通事故赔偿专题', 1, :case_source, 1,
            :start_date, :end_date, 20000.00, :emp_id, 1,
            '7月交通事故赔偿专题投放', :now, :now, 'active'
        )
        RETURNING id
    """), {"case_source": SOURCE_AD, "start_date": yesterday, "end_date": next_week, "emp_id": EMP_ZHANGSAN, "now": now}).scalar()

    # 2. 广告创意
    creative_id = conn.execute(text("""
        INSERT INTO oa.ops_ad_creative (
            campaign_id, asset_id, creative_no, creative_name, creative_type, platform,
            publish_url, material_summary, exposure_count, click_count, lead_count,
            ad_cost, creative_status, created_at, updated_at, remark
        ) VALUES (
            :campaign_id, NULL, 'CR20260709001', '交通事故赔偿-短视频创意A', 1, 1,
            'https://example.com/ad/1', '讲解交通事故赔偿流程与常见误区', 50000, 3200, 180,
            3500.00, 1, :now, :now, '测试创意'
        )
        RETURNING id
    """), {"campaign_id": campaign_id, "now": now}).scalar()

    # 3. 直播场次（7.8 晚间场）
    live_session_id = conn.execute(text("""
        INSERT INTO oa.ops_live_session (
            session_no, platform, live_title, legal_topic, comment_count,
            private_message_count, lead_count, conversion_count, ad_cost, data_summary,
            created_at, updated_at, status, remark, online_user_count, lead_conversion_rate,
            exposure_entry_rate, live_group, exposure_count, entry_user_count, valid_viewer_count,
            avg_watch_seconds, valid_lead_count, form_submit_count, private_message_user_count,
            exposure_entry_rate_calc_rule, lead_conversion_rate_calc_rule
        ) VALUES (
            'LS20260708001', '抖音', '交通事故赔偿在线答疑', '交通事故赔偿', 850,
            320, 45, 8, 2000.00, '7月8日晚间直播，主要解答交通事故赔偿问题',
            :now, :now, 'active', '测试直播', 1200, 0.0600,
            0.1600, 1, 8000, 1300, 980,
            180, 45, 60, 320,
            1, 1
        )
        RETURNING id
    """), {"now": now}).scalar()

    # 4. 广告日消耗
    conn.execute(text("""
        INSERT INTO oa.ops_ad_spend_daily (
            campaign_id, creative_id, spend_date, ad_cost, exposure_count, click_count,
            entry_user_count, lead_count, valid_lead_count, deal_amount, received_amount,
            cost_per_lead, roi_rate, created_at, updated_at, remark, live_session_id,
            cumulative_viewer_count, platform_snapshot, updated_by
        ) VALUES (
            :campaign_id, :creative_id, :today, 3500.00, 50000, 3200,
            1300, 180, 120, 400000.00, 50000.00,
            19.44, 14.29, :now, :now, '测试日消耗', :live_session_id,
            1200, '抖音', NULL
        )
    """), {"campaign_id": campaign_id, "creative_id": creative_id, "today": today, "live_session_id": live_session_id, "now": now})

    # ============================================================
    # 5. 创建三个当事人/客户
    # ============================================================
    parties = []
    for code, name, mobile, id_no, address in [
        ('P20260709002', '王五', '13911112222', '320722198505051234', '江苏省连云港市连云区'),
        ('P20260709003', '赵六', '13922223333', '320722199201011234', '江苏省连云港市赣榆区'),
        ('P20260709004', '孙七', '13933334444', '320722198808081234', '江苏省连云港市东海县'),
    ]:
        party_id = conn.execute(text("""
            INSERT INTO oa.party_main (
                party_code, party_type, party_name, gender, mobile, id_type, id_number,
                address, is_repeat_party, party_status, is_deleted, created_at, updated_at
            ) VALUES (
                :code, 1, :name, 1, :mobile, 1, :id_no,
                :address, 0, 1, 0, :now, :now
            )
            RETURNING id
        """), {"code": code, "name": name, "mobile": mobile, "id_no": id_no, "address": address, "now": now}).scalar()
        parties.append((party_id, name, mobile, id_no))

    clients = []
    for idx, (party_id, name, mobile, id_no) in enumerate(parties):
        owner = EMP_ZHANGSAN if idx % 2 == 0 else EMP_LISI
        client_id = conn.execute(text("""
            INSERT INTO oa.crm_client (
                client_no, client_type, id_card_no, client_level, risk_level, privacy_level,
                profile_summary, owner_employee_id, case_source, status, created_at, updated_at
            ) VALUES (
                :client_no, 'individual', :id_no, 'normal', 'low', 'normal',
                :summary, :owner, :source, 'active', :now, :now
            )
            RETURNING id
        """), {
            "client_no": f'C20260709{idx+2:03d}',
            "id_no": id_no,
            "summary": f'{name}（交通事故赔偿案件当事人）',
            "owner": owner,
            "source": SOURCE_LIVE if idx != 1 else SOURCE_AD,
            "now": now
        }).scalar()
        clients.append((client_id, name, owner))

    # ============================================================
    # 6. 创建三条线索（不同转化结果）
    # ============================================================
    leads = []
    lead_data = [
        # (client_idx, lead_no, title, source, owner, main_negotiator, status, deal_intention, deal_amount, received, balance)
        (0, 'L20260709002', '王五交通事故赔偿咨询', SOURCE_LIVE, EMP_ZHANGSAN, EMP_ZHANGSAN, 'converted', 4, 150000.00, 15000.00, 135000.00),
        (1, 'L20260709003', '赵六交通事故赔偿咨询', SOURCE_AD, EMP_LISI, EMP_LISI, 'following', 2, 0.00, 0.00, 0.00),
        (2, 'L20260709004', '孙七交通事故赔偿咨询', SOURCE_LIVE, EMP_ZHANGSAN, EMP_LISI, 'negotiation', 3, 80000.00, 0.00, 80000.00),
    ]

    for idx, (client_idx, lead_no, title, source, owner, main_neg, status, deal_int, deal_amt, received, balance) in enumerate(lead_data):
        client_id, client_name, _ = clients[client_idx]
        lead_id = conn.execute(text("""
            INSERT INTO oa.crm_lead (
                client_id, lead_no, lead_title, case_brief, demand_summary, urgency_level, lead_status,
                case_source, offline_expand_remark, owner_employee_id, owner_department_id,
                main_negotiator_id, assistant_negotiator_id, consultant_employee_id,
                case_type, deal_intention, deal_amount, received_amount, remaining_balance, balance_due_date,
                wechat_added_flag, wechat_added_at, wechat_added_by,
                key_case_flag, key_case_reason, is_duplicate_party, assigned_at, visit_at,
                created_at, updated_at, status
            ) VALUES (
                :client_id, :lead_no, :title,
                '2026年6月发生机动车交通事故，当事人对责任认定及赔偿标准存在疑问。',
                '希望了解赔偿项目、计算标准及委托流程。',
                'high', :status,
                :source, NULL, :owner, :dept,
                :main_neg, NULL, :owner,
                2, :deal_int, :deal_amt, :received, :balance, :next_week,
                1, :yesterday, :owner,
                0, '普通案件', 0, :yesterday, NULL,
                :now, :now, 'active'
            )
            RETURNING id
        """), {
            "client_id": client_id, "lead_no": lead_no, "title": title, "status": status, "source": source,
            "owner": owner, "dept": DEPT_MARKET, "main_neg": main_neg,
            "deal_int": deal_int, "deal_amt": deal_amt, "received": received, "balance": balance,
            "next_week": next_week, "yesterday": yesterday, "now": now
        }).scalar()
        leads.append((lead_id, client_id, client_name, status, source))

    # ============================================================
    # 7. 线索触点（直播/广告）
    # ============================================================
    for idx, (lead_id, _, _, _, source) in enumerate(leads):
        campaign = campaign_id if source == SOURCE_AD else None
        creative = creative_id if source == SOURCE_AD else None
        live = live_session_id if source == SOURCE_LIVE else None
        conn.execute(text("""
            INSERT INTO oa.lead_source_touch (
                lead_id, touch_channel, touch_time, touch_content,
                campaign_id, creative_id, asset_id, source_platform_user_id,
                is_first_touch, is_last_touch, conversion_contribution_amount,
                created_by, updated_at, updated_by, status, remark, created_at
            ) VALUES (
                :lead_id, :channel, :touch_time, :content,
                :campaign, :creative, NULL, :platform_user_id,
                1, 1, :contribution,
                :created_by, :now, :created_by, 'active', '首次触点', :now
            )
        """), {
            "lead_id": lead_id, "channel": source,
            "touch_time": yesterday, "content": '通过抖音渠道首次接触',
            "campaign": campaign, "creative": creative,
            "platform_user_id": f'user_{lead_id}',
            "contribution": 100.00 if idx != 1 else 0.00,
            "created_by": EMP_ZHANGSAN, "now": now
        })

    # ============================================================
    # 8. 线索下发
    # ============================================================
    for idx, (lead_id, _, _, _, _) in enumerate(leads):
        to_emp = EMP_ZHANGSAN if idx != 1 else EMP_LISI
        conn.execute(text("""
            INSERT INTO oa.lead_assignment_log (
                lead_id, from_department_id, to_department_id, from_employee_id,
                to_employee_id, assigned_by, assigned_at, accepted_at, assignment_status,
                assignment_reason, created_at, updated_at
            ) VALUES (
                :lead_id, :dept, :dept, :assigned_by,
                :to_emp, :assigned_by, :yesterday, :yesterday, 2,
                '根据线索来源和擅长领域分配', :now, :now
            )
        """), {
            "lead_id": lead_id, "dept": DEPT_MARKET, "assigned_by": EMP_ZHANGSAN,
            "to_emp": to_emp, "yesterday": yesterday, "now": now
        })

    # ============================================================
    # 9. 电话任务 + 任务项
    # ============================================================
    call_task_id = conn.execute(text("""
        INSERT INTO oa.mkt_call_task (
            task_name, batch_no, case_source, assigned_employee_id, planned_call_time,
            task_priority, task_status, script_version, planned_count, created_at, updated_at, status
        ) VALUES (
            '7.8直播线索电话回访', 'T20260708002', :source, :emp_id, :yesterday,
            'high', 'completed', 'v2.0', 50, :now, :now, 'active'
        )
        RETURNING id
    """), {"source": SOURCE_LIVE, "emp_id": EMP_ZHANGSAN, "yesterday": yesterday, "now": now}).scalar()

    for lead_id, client_id, client_name, _, _ in leads:
        conn.execute(text("""
            INSERT INTO oa.mkt_call_task_item (
                call_task_id, lead_id, client_id, assigned_employee_id, planned_call_time,
                item_status, last_call_time, last_call_result, remark, created_at, updated_at
            ) VALUES (
                :task_id, :lead_id, :client_id, :emp_id, :yesterday,
                'completed', :yesterday, 'connected', '已接通并邀约', :now, :now
            )
        """), {"task_id": call_task_id, "lead_id": lead_id, "client_id": client_id,
               "emp_id": EMP_ZHANGSAN, "yesterday": yesterday, "now": now})

    # ============================================================
    # 10. 电话记录 + 质检
    # ============================================================
    call_results = [
        (leads[0][0], leads[0][1], EMP_ZHANGSAN, 'visited', '当事人认可专业度，预约次日到所面谈，已添加微信。'),
        (leads[1][0], leads[1][1], EMP_LISI, 'not_connected', '当事人表示需要再考虑，约定一周后回访。'),
        (leads[2][0], leads[2][1], EMP_LISI, 'visited', '当事人有初步委托意向，预约到访谈案。'),
    ]

    call_record_ids = []
    for lead_id, client_id, caller, result, summary in call_results:
        record_id = conn.execute(text("""
            INSERT INTO oa.mkt_call_record (
                call_task_id, lead_id, caller_employee_id, call_direction, call_start_time,
                call_duration_seconds, call_result, call_connect_result, invitation_result,
                conversation_summary, next_action, appointment_created, created_at, updated_at
            ) VALUES (
                :task_id, :lead_id, :caller, 'outbound', :yesterday,
                420, :result, 'connected', :result,
                :summary, '跟进邀约', :appointment_created, :now, :now
            )
            RETURNING id
        """), {
            "task_id": call_task_id, "lead_id": lead_id, "caller": caller,
            "result": result, "summary": summary,
            "appointment_created": result == 'visited', "yesterday": yesterday, "now": now
        }).scalar()
        call_record_ids.append(record_id)

    # 电话质检（针对第一条和第三条成功邀约的记录）
    for i, record_id in enumerate(call_record_ids):
        if i == 1:
            continue
        reviewer = EMP_LISI if i == 0 else EMP_ZHANGSAN
        conn.execute(text("""
            INSERT INTO oa.mkt_call_quality_review (
                call_record_id, lead_id, reviewer_id, review_time, quality_review_status,
                quality_score, script_compliance_score, service_attitude_score, risk_words_detected,
                risk_words_detail, improvement_suggestion, review_comment, passed_flag,
                created_at, created_by, updated_at, updated_by, status, remark
            ) VALUES (
                :record_id, :lead_id, :reviewer, :now, 1,
                92.5, 95.0, 90.0, 0,
                NULL, '继续保持专业话术', '话术规范、服务态度良好', 1,
                :now, :reviewer, :now, :reviewer, 'active', '质检通过'
            )
        """), {"record_id": record_id, "lead_id": leads[i][0], "reviewer": reviewer, "now": now})

    # ============================================================
    # 11. 预约到访 + 变更
    # ============================================================
    # 案例A：王五，正常到访并签约
    appointment_a = conn.execute(text("""
        INSERT INTO oa.mkt_appointment (
            client_id, lead_id, appointment_type, appointment_time, actual_arrival_time,
            reception_employee_id, lawyer_employee_id, legal_category, appointment_status,
            visit_result, reschedule_count, visit_sequence, appointment_source, confirmation_status,
            created_at, updated_at, status
        ) VALUES (
            :client_id, :lead_id, 'visit', :yesterday, :yesterday,
            :emp_id, :emp_id, '交通事故', 'completed',
            'signed', 0, 1, :source, 2,
            :now, :now, 'active'
        )
        RETURNING id
    """), {"client_id": leads[0][1], "lead_id": leads[0][0], "emp_id": EMP_ZHANGSAN,
           "source": SOURCE_LIVE, "yesterday": yesterday, "now": now}).scalar()

    # 案例C：孙七，改期后到访但未签约
    appointment_c = conn.execute(text("""
        INSERT INTO oa.mkt_appointment (
            client_id, lead_id, appointment_type, appointment_time, actual_arrival_time,
            reception_employee_id, lawyer_employee_id, legal_category, appointment_status,
            visit_result, reschedule_count, visit_sequence, appointment_source, confirmation_status,
            created_at, updated_at, status
        ) VALUES (
            :client_id, :lead_id, 'visit', :today, :today,
            :emp_id, :emp_id, '交通事故', 'completed',
            'not_signed', 1, 2, :source, 2,
            :now, :now, 'active'
        )
        RETURNING id
    """), {"client_id": leads[2][1], "lead_id": leads[2][0], "emp_id": EMP_LISI,
           "source": SOURCE_LIVE, "today": today, "now": now}).scalar()

    # 孙七的预约变更记录（昨天改到今天）
    conn.execute(text("""
        INSERT INTO oa.mkt_appointment_change_log (
            appointment_id, lead_id, change_type, old_appointment_time, new_appointment_time,
            actual_arrival_time, no_show_reason_type, no_show_reason_detail, changed_by,
            changed_at, confirmation_status, visit_sequence, created_at, updated_at, remark
        ) VALUES (
            :appointment_id, :lead_id, 1, :yesterday, :today,
            :today, NULL, NULL, :changed_by,
            :yesterday, 2, 1, :now, :now, '当事人临时有事，改期到今天'
        )
    """), {"appointment_id": appointment_c, "lead_id": leads[2][0], "yesterday": yesterday,
           "today": today, "changed_by": EMP_LISI, "now": now})

    # ============================================================
    # 12. 跟进记录
    # ============================================================
    # 赵六的跟进记录
    conn.execute(text("""
        INSERT INTO oa.crm_follow_up (
            lead_id, client_id, follow_employee_id, follow_time, follow_method,
            follow_content, customer_feedback, next_action, next_follow_time, follow_result,
            created_at, created_by, updated_at, updated_by, status, remark
        ) VALUES (
            :lead_id, :client_id, :emp_id, :yesterday, 'phone',
            '电话回访，了解当事人对委托的顾虑。', '当事人担心费用问题，希望先了解收费标准。', '发送报价方案并预约到访', :tomorrow, 'pending',
            :now, :emp_id, :now, :emp_id, 'active', '需持续跟进'
        )
    """), {"lead_id": leads[1][0], "client_id": leads[1][1], "emp_id": EMP_LISI,
           "yesterday": yesterday, "tomorrow": tomorrow, "now": now})

    # ============================================================
    # 13. 咨询记录
    # ============================================================
    # 王五的咨询记录（已转化）
    conn.execute(text("""
        INSERT INTO oa.crm_consultation (
            lead_id, client_id, consultation_type, consultation_time, consultant_employee_id,
            materials_received, conversion_intention, result_status, converted_case_id,
            created_at, created_by, updated_at, updated_by
        ) VALUES (
            :lead_id, :client_id, 'visit', :yesterday, :emp_id,
            '事故认定书、医疗票据、身份证复印件', 'high', 'converted', NULL,
            :now, :emp_id, :now, :emp_id
        )
    """), {"lead_id": leads[0][0], "client_id": leads[0][1], "emp_id": EMP_ZHANGSAN,
           "yesterday": yesterday, "now": now})

    # ============================================================
    # 14. 谈案记录
    # ============================================================
    # 王五，成功签约
    conn.execute(text("""
        INSERT INTO oa.lead_negotiation_record (
            lead_id, appointment_id, negotiation_time, main_negotiator_id, assistant_negotiator_id,
            participants, deal_intention, deal_amount, received_amount, customer_objection,
            negotiation_result, lost_reason_type, next_action, next_follow_up_at, recording_attachment_id,
            key_case_flag, key_case_reason, payment_terms_snapshot, created_at, updated_at
        ) VALUES (
            :lead_id, :appointment_id, :yesterday, :main_neg, NULL,
            '张三、王五', 4, 150000.00, 15000.00, '对律师费比例有疑问',
            1, NULL, '签约并移交案管', :today, NULL,
            0, '普通案件', '风险代理：前期1.5万元，回款后按10%收取。', :now, :now
        )
    """), {"lead_id": leads[0][0], "appointment_id": appointment_a, "main_neg": EMP_ZHANGSAN,
           "yesterday": yesterday, "today": today, "now": now})

    # 孙七，未签约
    conn.execute(text("""
        INSERT INTO oa.lead_negotiation_record (
            lead_id, appointment_id, negotiation_time, main_negotiator_id, assistant_negotiator_id,
            participants, deal_intention, deal_amount, received_amount, customer_objection,
            negotiation_result, lost_reason_type, next_action, next_follow_up_at, recording_attachment_id,
            key_case_flag, key_case_reason, payment_terms_snapshot, created_at, updated_at
        ) VALUES (
            :lead_id, :appointment_id, :today, :main_neg, NULL,
            '李四、孙七', 2, 0.00, 0.00, '认为律师费过高，需要比较其他律所',
            2, 1, '一周后回访', :next_week, NULL,
            0, '普通案件', '未达成付费方案', :now, :now
        )
    """), {"lead_id": leads[2][0], "appointment_id": appointment_c, "main_neg": EMP_LISI,
           "today": today, "next_week": next_week, "now": now})

    # ============================================================
    # 15. 合同撰写与审批（市场拓展部完成签约手续）
    # ============================================================
    # 王五，成功签约：起草委托代理合同并审批
    contract_id = conn.execute(text("""
        INSERT INTO oa.admin_contract (
            contract_no, contract_title, contract_type, counterparty_name, amount,
            created_at, created_by, updated_at, updated_by, remark
        ) VALUES (
            'CO20260709001', '王五交通事故赔偿案件委托代理合同', '委托代理', '王五',
            150000.00, :now, :emp_id, :now, :emp_id, '市场拓展部张三起草'
        )
        RETURNING id
    """), {"emp_id": EMP_ZHANGSAN, "now": now}).scalar()

    conn.execute(text("""
        INSERT INTO oa.sys_approval_record (
            approval_no, approval_type, applicant_employee_id, approver_employee_id,
            approval_opinion, approval_status, created_at, created_by, updated_at,
            updated_by, status, remark
        ) VALUES (
            'AP20260709001', 'contract_approval', :emp_id, :approver_id,
            '合同条款符合律所标准，同意签署。', 'approved', :now, :emp_id, :now,
            :approver_id, 'active', '委托代理合同审批'
        )
    """), {"emp_id": EMP_ZHANGSAN, "approver_id": EMP_LISI, "now": now})

    # ============================================================
    # 16. KPI 目标 + 结果（张三、李四 7月）
    # ============================================================
    kpi_targets = []
    for emp_id in [EMP_ZHANGSAN, EMP_LISI]:
        target_id = conn.execute(text("""
            INSERT INTO oa.mkt_employee_kpi_target (
                employee_id, department_id, target_month, lead_target_count, call_target_count,
                connected_target_count, appointment_target_count, visit_target_count, deal_target_count,
                deal_amount_target, received_amount_target, follow_up_target_count, quality_score_target,
                kpi_status, created_at, created_by, updated_at, updated_by, status, remark
            ) VALUES (
                :emp_id, :dept, '2026-07', 50, 200,
                120, 30, 20, 5,
                300000.00, 100000.00, 50, 90.0,
                1, :now, :created_by, :now, :created_by, 'active', '7月市场拓展部KPI目标'
            )
            RETURNING id
        """), {"emp_id": emp_id, "dept": DEPT_MARKET, "created_by": EMP_ZHANGSAN, "now": now}).scalar()
        kpi_targets.append((target_id, emp_id))

    # KPI 结果
    kpi_results = [
        # 张三：线索3条，电话3通，接通3通，预约2个，到访2个，成交1个，成交额15万，回款1.5万
        (EMP_ZHANGSAN, kpi_targets[0][0], 3, 3, 3, 2, 2, 1, 150000.00, 15000.00, 1, 92.5),
        # 李四：线索2条，电话2通，接通2通，预约1个，到访1个，成交0个，成交额0，回款0
        (EMP_LISI, kpi_targets[1][0], 2, 2, 2, 1, 1, 0, 0.00, 0.00, 2, 0.0),
    ]
    for emp_id, target_id, lead_cnt, call_cnt, conn_cnt, appt_cnt, visit_cnt, deal_cnt, deal_amt, recv_amt, follow_cnt, avg_score in kpi_results:
        completion = round((deal_amt / 300000.00) * 100, 2) if deal_amt > 0 else 0.00
        conn.execute(text("""
            INSERT INTO oa.mkt_employee_kpi_result (
                employee_id, department_id, result_month, lead_actual_count, call_actual_count,
                connected_actual_count, appointment_actual_count, visit_actual_count, deal_actual_count,
                deal_amount_actual, received_amount_actual, follow_up_actual_count, avg_quality_score,
                target_id, completion_rate, kpi_result_status, confirmed_by, confirmed_at,
                created_at, remark, created_by, updated_by, updated_at
            ) VALUES (
                :emp_id, :dept, '2026-07', :lead_cnt, :call_cnt,
                :conn_cnt, :appt_cnt, :visit_cnt, :deal_cnt,
                :deal_amt, :recv_amt, :follow_cnt, :avg_score,
                :target_id, :completion, 1, :confirmed_by, :now,
                :now, '7月市场拓展部KPI结果', :confirmed_by, :confirmed_by, :now
            )
        """), {
            "emp_id": emp_id, "dept": DEPT_MARKET, "lead_cnt": lead_cnt, "call_cnt": call_cnt,
            "conn_cnt": conn_cnt, "appt_cnt": appt_cnt, "visit_cnt": visit_cnt, "deal_cnt": deal_cnt,
            "deal_amt": deal_amt, "recv_amt": recv_amt, "follow_cnt": follow_cnt, "avg_score": avg_score,
            "target_id": target_id, "completion": completion, "confirmed_by": EMP_ZHANGSAN, "now": now
        })

    print("市场拓展部整体流程测试数据插入完成：")
    print(f"  广告投放计划 campaign_id={campaign_id}")
    print(f"  广告创意 creative_id={creative_id}")
    print(f"  直播场次 live_session_id={live_session_id}")
    print(f"  电话任务 call_task_id={call_task_id}")
    print(f"  线索A（王五，已签约） lead_id={leads[0][0]}, appointment_id={appointment_a}")
    print(f"  线索B（赵六，跟进中） lead_id={leads[1][0]}")
    print(f"  线索C（孙七，未签约） lead_id={leads[2][0]}, appointment_id={appointment_c}")
    print(f"  KPI目标 target_ids={[t[0] for t in kpi_targets]}")
