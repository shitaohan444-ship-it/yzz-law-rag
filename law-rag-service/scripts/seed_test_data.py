"""
填充律所 OA 测试数据。

生成两组完整的业务流：
1. 直播线索 → 电邀 → 预约到访 → 谈案 → 签约 → 案件 → 回款 → 调档
2. 线下拓展线索 → 谈案 → 签约 → 案件

Usage:
    .venv\Scripts\python.exe scripts\seed_test_data.py
"""
from __future__ import annotations

import sys
from datetime import datetime, date, timedelta
from pathlib import Path

from sqlalchemy import create_engine, text

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import settings

engine = create_engine(
    settings.database_url_with_search_path,
    echo=False,
    future=True,
)

TEST_TAG = "【测试数据】"


def clean_test_data(conn) -> None:
    """删除之前由本脚本插入的测试数据。"""
    # 按依赖反向顺序删除
    conn.execute(text("DELETE FROM oa.legal_deadline WHERE remark LIKE :tag"), {"tag": f"%{TEST_TAG}%"})
    conn.execute(text("DELETE FROM oa.case_retrieval_task_log WHERE remark LIKE :tag"), {"tag": f"%{TEST_TAG}%"})
    conn.execute(text("DELETE FROM oa.case_retrieval_task WHERE remark LIKE :tag"), {"tag": f"%{TEST_TAG}%"})
    conn.execute(text("DELETE FROM oa.case_status_log WHERE remark LIKE :tag"), {"tag": f"%{TEST_TAG}%"})
    conn.execute(text("DELETE FROM oa.case_assignment WHERE remark LIKE :tag"), {"tag": f"%{TEST_TAG}%"})
    conn.execute(text("DELETE FROM oa.fin_payment_record WHERE remark LIKE :tag"), {"tag": f"%{TEST_TAG}%"})
    conn.execute(text("DELETE FROM oa.fin_payment_plan WHERE id IN (1, 2, 3, 4, 5)"))
    conn.execute(text("DELETE FROM oa.fin_invoice WHERE remark LIKE :tag"), {"tag": f"%{TEST_TAG}%"})
    conn.execute(text("DELETE FROM oa.fin_refund_record WHERE remark LIKE :tag"), {"tag": f"%{TEST_TAG}%"})
    conn.execute(text("DELETE FROM oa.fin_fee_agreement WHERE remark LIKE :tag"), {"tag": f"%{TEST_TAG}%"})
    conn.execute(text("DELETE FROM oa.case_main WHERE remark LIKE :tag"), {"tag": f"%{TEST_TAG}%"})
    conn.execute(text("DELETE FROM oa.lead_negotiation_record WHERE remark LIKE :tag"), {"tag": f"%{TEST_TAG}%"})
    conn.execute(text("DELETE FROM oa.mkt_appointment WHERE remark LIKE :tag"), {"tag": f"%{TEST_TAG}%"})
    conn.execute(text("DELETE FROM oa.mkt_call_record WHERE id IN (1, 2)"))
    conn.execute(text("DELETE FROM oa.lead_source_touch WHERE remark LIKE :tag"), {"tag": f"%{TEST_TAG}%"})
    conn.execute(text("DELETE FROM oa.crm_lead WHERE remark LIKE :tag"), {"tag": f"%{TEST_TAG}%"})
    conn.execute(text("DELETE FROM oa.ops_ad_spend_daily WHERE remark LIKE :tag"), {"tag": f"%{TEST_TAG}%"})
    conn.execute(text("DELETE FROM oa.ops_ad_campaign WHERE remark LIKE :tag"), {"tag": f"%{TEST_TAG}%"})
    conn.execute(text("DELETE FROM oa.ops_live_session WHERE remark LIKE :tag"), {"tag": f"%{TEST_TAG}%"})
    conn.execute(text("DELETE FROM oa.crm_client WHERE remark LIKE :tag"), {"tag": f"%{TEST_TAG}%"})
    conn.execute(text("DELETE FROM oa.party_main WHERE remark LIKE :tag"), {"tag": f"%{TEST_TAG}%"})
    # 部门负责人在员工删除前先清理，避免外键冲突
    conn.execute(text("UPDATE oa.sys_department SET manager_employee_id = NULL WHERE remark LIKE :tag"), {"tag": f"%{TEST_TAG}%"})
    conn.execute(text("DELETE FROM oa.sys_employee WHERE remark LIKE :tag"), {"tag": f"%{TEST_TAG}%"})
    conn.execute(text("DELETE FROM oa.sys_department WHERE remark LIKE :tag"), {"tag": f"%{TEST_TAG}%"})
    print("[seed] Cleaned existing test data")


def insert_departments(conn):
    conn.execute(
        text("""
            INSERT INTO oa.sys_department (id, department_name, department_code, department_type, sort_order, status, remark, created_at, updated_at)
            VALUES
                (1, '市场拓展部', 'MKT', 'business', 1, 'active', :remark, NOW(), NOW()),
                (2, '案件管理部', 'CASE', 'business', 2, 'active', :remark, NOW(), NOW()),
                (3, '律师部', 'LAW', 'business', 3, 'active', :remark, NOW(), NOW())
            ON CONFLICT (id) DO NOTHING
        """),
        {"remark": TEST_TAG},
    )
    print("[seed] Inserted departments")


def insert_employees(conn):
    now = datetime.now()
    conn.execute(
        text("""
            INSERT INTO oa.sys_employee (
                id, employee_no, real_name, gender, department_id, position_name,
                employment_status, join_date, status, remark, created_at, updated_at
            )
            VALUES
                (1, 'E001', '张三', 'male', 1, '电邀专员', 'active', :join_date, 'active', :remark, :now, :now),
                (2, 'E002', '李四', 'male', 1, '谈案顾问', 'active', :join_date, 'active', :remark, :now, :now),
                (3, 'E003', '王五', 'female', 2, '案管专员', 'active', :join_date, 'active', :remark, :now, :now),
                (4, 'E004', '赵六', 'male', 3, '主办律师', 'active', :join_date, 'active', :remark, :now, :now)
            ON CONFLICT (id) DO NOTHING
        """),
        {
            "join_date": date(2024, 1, 1),
            "remark": TEST_TAG,
            "now": now,
        },
    )
    # 更新部门负责人（打破循环依赖）
    conn.execute(
        text("""
            UPDATE oa.sys_department
            SET manager_employee_id = CASE id
                WHEN 1 THEN 2
                WHEN 2 THEN 3
                WHEN 3 THEN 4
            END,
            updated_at = NOW()
            WHERE id IN (1, 2, 3)
        """)
    )
    print("[seed] Inserted employees")


def insert_parties(conn):
    now = datetime.now()
    conn.execute(
        text("""
            INSERT INTO oa.party_main (
                id, party_code, party_type, party_name, gender, mobile,
                first_source, party_status, is_deleted, is_repeat_party, remark, created_at, updated_at
            )
            VALUES
                (1, 'P001', 1, '陈先生', 1, '13800000001', 2, 1, 0, 0, :remark, :now, :now),
                (2, 'P002', 2, '刘女士', 2, '13900000002', 10, 1, 0, 0, :remark, :now, :now)
            ON CONFLICT (id) DO NOTHING
        """),
        {"remark": TEST_TAG, "now": now},
    )
    print("[seed] Inserted parties")


def insert_clients(conn):
    now = datetime.now()
    conn.execute(
        text("""
            INSERT INTO oa.crm_client (
                id, client_no, client_type, id_card_no, case_source,
                first_contact_time, client_level, risk_level, privacy_level,
                profile_summary, owner_employee_id, status, remark, created_at, updated_at
            )
            VALUES
                (3, 'C001', 'individual', '320102199001011234', 2,
                 :first_contact1, 'A', '中', 'normal',
                 '陈先生', 1, 'active', :remark, :now, :now),
                (4, 'C002', 'individual', '320102199502023456', 10,
                 :first_contact2, 'A', '高', 'normal',
                 '刘女士', 2, 'active', :remark, :now, :now)
            ON CONFLICT (id) DO NOTHING
        """),
        {
            "first_contact1": datetime(2026, 7, 1, 19, 30, 0),
            "first_contact2": datetime(2026, 7, 2, 9, 30, 0),
            "remark": TEST_TAG,
            "now": now,
        },
    )
    print("[seed] Inserted clients")


def insert_live_and_campaign(conn):
    now = datetime.now()
    conn.execute(
        text("""
            INSERT INTO oa.ops_live_session (
                id, session_no, platform, live_title, legal_topic,
                comment_count, private_message_count, lead_count, conversion_count,
                exposure_count, entry_user_count, valid_viewer_count, valid_lead_count,
                online_user_count, private_message_user_count, form_submit_count,
                lead_conversion_rate, exposure_entry_rate,
                avg_watch_seconds, ad_cost, status, remark, created_at, updated_at
            )
            VALUES (
                1, 'LS20260701001', '抖音', '劳动合同纠纷在线答疑', '劳动纠纷',
                120, 80, 45, 5,
                5000, 800, 1000, 30,
                1200, 60, 20,
                0.0600, 0.1600,
                600, 2000.00, 'active', :remark, :created_at, :now
            )
            ON CONFLICT (id) DO NOTHING
        """),
        {
            "remark": TEST_TAG,
            "created_at": datetime(2026, 7, 1, 19, 0, 0),
            "now": now,
        },
    )
    conn.execute(
        text("""
            INSERT INTO oa.ops_ad_campaign (
                id, campaign_no, campaign_name, platform, case_source, campaign_type,
                start_date, end_date, budget_amount, owner_employee_id, campaign_status,
                status, remark, created_at, updated_at
            )
            VALUES (
                1, 'C20260701001', '抖音本地推-劳动纠纷', 1, 2, 1,
                :start_date, :end_date, 10000.00, 2, 1,
                'active', :remark, :now, :now
            )
            ON CONFLICT (id) DO NOTHING
        """),
        {
            "start_date": date(2026, 7, 1),
            "end_date": date(2026, 7, 31),
            "remark": TEST_TAG,
            "now": now,
        },
    )
    conn.execute(
        text("""
            INSERT INTO oa.ops_ad_spend_daily (
                id, campaign_id, spend_date, ad_cost, exposure_count,
                click_count, entry_user_count, lead_count, valid_lead_count,
                deal_amount, received_amount,
                live_session_id, cumulative_viewer_count, platform_snapshot,
                remark, created_at, updated_at
            )
            VALUES (
                1, 1, :spend_date, 2000.00, 5000, 1200, 800, 45, 30,
                50000.00, 20000.00,
                1, 1200, '抖音', :remark, :now, :now
            )
            ON CONFLICT (id) DO NOTHING
        """),
        {
            "spend_date": date(2026, 7, 1),
            "remark": TEST_TAG,
            "now": now,
        },
    )
    print("[seed] Inserted live session and campaign data")


def insert_leads(conn):
    now = datetime.now()
    conn.execute(
        text("""
            INSERT INTO oa.crm_lead (
                id, client_id, lead_no, lead_title, source_detail, legal_category,
                case_brief, urgency_level, lead_status, owner_employee_id, assigned_at,
                case_source, case_type, deal_intention, primary_party_id,
                wechat_added_flag, wechat_added_at, wechat_added_by,
                key_case_flag, key_case_reason, consultant_employee_id,
                is_duplicate_party, main_negotiator_id, assistant_negotiator_id,
                deal_amount, received_amount, remaining_balance, visit_at,
                status, remark, created_at, updated_at
            )
            VALUES
                (
                    1, 3, 'L20260701001', '陈先生劳动纠纷咨询', '抖音直播', '劳动纠纷',
                    '公司违法解除劳动合同，要求赔偿2N', '高', 'deal', 1, :assigned_at,
                    2, 1, 3, 1,
                    1, :wechat_at1, 1,
                    0, '', 1,
                    0, 2, NULL,
                    50000.00, 20000.00, 30000.00, :visit_at,
                    'active', :remark, :created_at, :now
                ),
                (
                    2, 4, 'L20260702001', '刘女士离婚财产分割咨询', '线下地推', '婚姻家事',
                    '离婚涉及房产分割和抚养权争议', '高', 'deal', 2, :assigned_at2,
                    10, 2, 3, 2,
                    0, :wechat_at2, 2,
                    1, '涉及大额财产', 2,
                    0, 2, NULL,
                    80000.00, 50000.00, 30000.00, :visit_at2,
                    'active', :remark, :created_at2, :now
                )
            ON CONFLICT (id) DO NOTHING
        """),
        {
            "assigned_at": datetime(2026, 7, 1, 20, 0, 0),
            "assigned_at2": datetime(2026, 7, 2, 9, 0, 0),
            "wechat_at1": datetime(2026, 7, 1, 20, 5, 0),
            "wechat_at2": datetime(2026, 7, 2, 9, 5, 0),
            "visit_at": datetime(2026, 7, 2, 14, 0, 0),
            "visit_at2": datetime(2026, 7, 3, 10, 0, 0),
            "created_at": datetime(2026, 7, 1, 19, 30, 0),
            "created_at2": datetime(2026, 7, 2, 9, 30, 0),
            "remark": TEST_TAG,
            "now": now,
        },
    )
    conn.execute(
        text("""
            INSERT INTO oa.lead_source_touch (
                lead_id, touch_channel, touch_time, campaign_id,
                is_first_touch, is_last_touch, conversion_contribution_amount,
                status, remark, created_at, updated_at
            )
            VALUES
                (1, 2, :touch_time1, 1, 1, 1, 50000.00, 'active', :remark, :now, :now),
                (2, 10, :touch_time2, NULL, 1, 1, 80000.00, 'active', :remark, :now, :now)
            ON CONFLICT DO NOTHING
        """),
        {
            "touch_time1": datetime(2026, 7, 1, 19, 35, 0),
            "touch_time2": datetime(2026, 7, 2, 9, 15, 0),
            "remark": TEST_TAG,
            "now": now,
        },
    )
    print("[seed] Inserted leads")


def insert_calls_and_appointments(conn):
    now = datetime.now()
    conn.execute(
        text("""
            INSERT INTO oa.mkt_call_record (
                id, lead_id, caller_employee_id, call_direction, call_start_time, call_duration_seconds,
                call_connect_result, call_result, conversation_summary,
                appointment_created, created_at, updated_at
            )
            VALUES
                (1, 1, 1, 'outbound', :call_time1, 300, 'connected', 'invited',
                 '【测试数据】客户有明确意向，已预约次日到访', TRUE, :now, :now),
                (2, 2, 1, 'outbound', :call_time2, 180, 'connected', 'invited',
                 '【测试数据】客户在外地，约定线上先沟通', FALSE, :now, :now)
            ON CONFLICT (id) DO NOTHING
        """),
        {
            "call_time1": datetime(2026, 7, 1, 10, 0, 0),
            "call_time2": datetime(2026, 7, 2, 14, 0, 0),
            "remark": TEST_TAG,
            "now": now,
        },
    )
    conn.execute(
        text("""
            INSERT INTO oa.mkt_appointment (
                id, client_id, lead_id, appointment_type, appointment_time, actual_arrival_time,
                reception_employee_id, lawyer_employee_id, legal_category,
                appointment_status, visit_result, reschedule_count, confirmation_status, appointment_source, visit_sequence,
                status, remark, created_at, updated_at
            )
            VALUES
                (1, 3, 1, 'visit', :apt_time1, :arrival_time1,
                 2, NULL, '劳动纠纷', 'completed', 'visited', 0, 1, 1, 1,
                 'active', :remark, :now, :now),
                (2, 4, 2, 'visit', :apt_time2, :arrival_time2,
                 2, NULL, '婚姻家事', 'completed', 'visited', 0, 1, 1, 1,
                 'active', :remark, :now, :now)
            ON CONFLICT (id) DO NOTHING
        """),
        {
            "apt_time1": datetime(2026, 7, 2, 14, 0, 0),
            "arrival_time1": datetime(2026, 7, 2, 14, 10, 0),
            "apt_time2": datetime(2026, 7, 3, 10, 0, 0),
            "arrival_time2": datetime(2026, 7, 3, 10, 5, 0),
            "remark": TEST_TAG,
            "now": now,
        },
    )
    print("[seed] Inserted calls and appointments")


def insert_negotiations(conn):
    now = datetime.now()
    conn.execute(
        text("""
            INSERT INTO oa.lead_negotiation_record (
                id, lead_id, appointment_id, negotiation_time, main_negotiator_id,
                assistant_negotiator_id, deal_intention, deal_amount, received_amount,
                negotiation_result, payment_terms_snapshot, key_case_flag, key_case_reason,
                remark, created_at, updated_at
            )
            VALUES
                (1, 1, 1, :neg_time1, 2, NULL, 3, 50000.00, 20000.00,
                 1, '签约时支付2万，余款3万于30日内付清', 0, '',
                 :remark, :now, :now),
                (2, 2, 2, :neg_time2, 2, NULL, 3, 80000.00, 50000.00,
                 1, '签约时支付5万，余款3万分两期支付', 1, '涉及大额财产分割',
                 :remark, :now, :now)
            ON CONFLICT (id) DO NOTHING
        """),
        {
            "neg_time1": datetime(2026, 7, 2, 15, 0, 0),
            "neg_time2": datetime(2026, 7, 3, 11, 0, 0),
            "remark": TEST_TAG,
            "now": now,
        },
    )
    print("[seed] Inserted negotiations")


def insert_cases(conn):
    now = datetime.now()
    conn.execute(
        text("""
            INSERT INTO oa.case_main (
                id, case_no, case_title, client_id, case_stage, case_status,
                main_lawyer_id, case_manager_id, lawyer_assistant_name,
                case_type, accept_date, case_brief, conflict_check_status, important_level,
                status, remark, created_at, updated_at
            )
            VALUES
                (1, 'C20260702001', '陈先生诉某公司劳动合同纠纷案', 3, 'accepted', 'active',
                 4, 3, '小张', 1, :accept_date1, '公司违法解除劳动合同', 'passed', 'normal',
                 'active', :remark, :now, :now),
                (2, 'C20260703001', '刘女士离婚财产分割案', 4, 'accepted', 'active',
                 4, 3, '小李', 2, :accept_date2, '离婚房产分割及抚养权', 'passed', 'high',
                 'active', :remark, :now, :now)
            ON CONFLICT (id) DO NOTHING
        """),
        {
            "accept_date1": date(2026, 7, 2),
            "accept_date2": date(2026, 7, 3),
            "remark": TEST_TAG,
            "now": now,
        },
    )
    # 案件分配
    conn.execute(
        text("""
            INSERT INTO oa.case_assignment (case_id, assigned_role, employee_id, assigned_at, status, remark, created_at, updated_at)
            VALUES
                (1, 'main_lawyer', 4, :assigned_at, 'active', :remark, :now, :now),
                (1, 'case_manager', 3, :assigned_at, 'active', :remark, :now, :now),
                (2, 'main_lawyer', 4, :assigned_at, 'active', :remark, :now, :now),
                (2, 'case_manager', 3, :assigned_at, 'active', :remark, :now, :now)
            ON CONFLICT DO NOTHING
        """),
        {"assigned_at": now, "remark": TEST_TAG, "now": now},
    )
    # 案件状态日志
    conn.execute(
        text("""
            INSERT INTO oa.case_status_log (
                case_id, from_stage, to_stage, from_status, to_status,
                progress_summary, changed_by, changed_at, customer_visible, status, remark, created_at, updated_at
            )
            VALUES
                (1, 'new', 'accepted', 'new', 'active', '已收案并分配主办律师', 3, :changed_at, FALSE, 'active', :remark, :now, :now),
                (2, 'new', 'accepted', 'new', 'active', '已收案并分配主办律师', 3, :changed_at, FALSE, 'active', :remark, :now, :now)
            ON CONFLICT DO NOTHING
        """),
        {"changed_at": now, "remark": TEST_TAG, "now": now},
    )
    print("[seed] Inserted cases")


def insert_financials(conn):
    now = datetime.now()
    conn.execute(
        text("""
            INSERT INTO oa.fin_fee_agreement (
                id, agreement_no, case_id, client_id, contract_no, fee_type,
                agreement_amount, currency, sign_date, responsible_employee_id, agreement_status,
                status, remark, created_at, updated_at
            )
            VALUES
                (1, 'A20260702001', 1, 3, 'CON20260702001', '固定收费', 50000.00, 'CNY', :sign_date1, 2, 'signed', 'active', :remark, :now, :now),
                (2, 'A20260703001', 2, 4, 'CON20260703001', '固定收费', 80000.00, 'CNY', :sign_date2, 2, 'signed', 'active', :remark, :now, :now)
            ON CONFLICT (id) DO NOTHING
        """),
        {
            "sign_date1": date(2026, 7, 2),
            "sign_date2": date(2026, 7, 3),
            "remark": TEST_TAG,
            "now": now,
        },
    )
    conn.execute(
        text("""
            INSERT INTO oa.fin_payment_plan (
                id, payment_plan_no, fee_agreement_id, case_id, plan_name,
                receivable_amount, due_date, received_amount, payment_node_status,
                status, created_at, updated_at
            )
            VALUES
                (1, 'PP20260702001', 1, 1, '首期款', 20000.00, :due_date1, 20000.00, 3, 'active', :now, :now),
                (2, 'PP20260702002', 1, 1, '尾款', 30000.00, :due_date2, 0.00, 1, 'active', :now, :now),
                (3, 'PP20260703001', 2, 2, '首期款', 50000.00, :due_date3, 50000.00, 3, 'active', :now, :now),
                (4, 'PP20260703002', 2, 2, '二期款', 20000.00, :due_date4, 0.00, 1, 'active', :now, :now),
                (5, 'PP20260703003', 2, 2, '三期款', 10000.00, :due_date5, 0.00, 1, 'active', :now, :now)
            ON CONFLICT (id) DO NOTHING
        """),
        {
            "due_date1": date(2026, 7, 2),
            "due_date2": date(2026, 8, 1),
            "due_date3": date(2026, 7, 3),
            "due_date4": date(2026, 8, 3),
            "due_date5": date(2026, 9, 3),
            "remark": TEST_TAG,
            "now": now,
        },
    )
    conn.execute(
        text("""
            INSERT INTO oa.fin_payment_record (
                id, payment_plan_id, case_id, client_id, received_amount,
                received_at, payment_method, confirm_status, status, remark, created_at, updated_at
            )
            VALUES
                (1, 1, 1, 3, 20000.00, :received_at1, 'bank_transfer', 'confirmed', 'active', :remark, :now, :now),
                (2, 3, 2, 4, 50000.00, :received_at2, 'bank_transfer', 'confirmed', 'active', :remark, :now, :now)
            ON CONFLICT (id) DO NOTHING
        """),
        {
            "received_at1": datetime(2026, 7, 2, 16, 0, 0),
            "received_at2": datetime(2026, 7, 3, 12, 0, 0),
            "remark": TEST_TAG,
            "now": now,
        },
    )
    conn.execute(
        text("""
            INSERT INTO oa.fin_invoice (
                id, case_id, client_id, invoice_title, invoice_type, invoice_amount,
                invoice_status, issued_at, status, remark, created_at, updated_at
            )
            VALUES
                (1, 1, 3, '陈先生', 'normal', 20000.00, 'issued', :issued_at1, 'active', :remark, :now, :now),
                (2, 2, 4, '刘女士', 'normal', 50000.00, 'issued', :issued_at2, 'active', :remark, :now, :now)
            ON CONFLICT (id) DO NOTHING
        """),
        {
            "issued_at1": datetime(2026, 7, 3, 10, 0, 0),
            "issued_at2": datetime(2026, 7, 4, 10, 0, 0),
            "remark": TEST_TAG,
            "now": now,
        },
    )
    print("[seed] Inserted financial data")


def insert_retrievals_and_deadlines(conn):
    now = datetime.now()
    conn.execute(
        text("""
            INSERT INTO oa.case_retrieval_task (
                id, case_id, task_no, target_unit_type, target_unit_name,
                retrieval_matter, assigned_lawyer_id, deadline_at, task_status,
                result_status, review_status, nas_path, status, remark, created_at, updated_at
            )
            VALUES
                (1, 1, 'RT20260702001', '法院', '某区人民法院', '调取劳动合同及解除通知书',
                 4, :deadline_at1, 'in_progress', 'pending', 'pending', '/cases/C20260702001/retrieval/', 'active', :remark, :now, :now),
                (2, 2, 'RT20260703001', '民政局', '某区民政局', '调取婚姻登记信息',
                 4, :deadline_at2, 'in_progress', 'pending', 'pending', '/cases/C20260703001/retrieval/', 'active', :remark, :now, :now)
            ON CONFLICT (id) DO NOTHING
        """),
        {
            "deadline_at1": datetime(2026, 7, 15, 17, 0, 0),
            "deadline_at2": datetime(2026, 7, 20, 17, 0, 0),
            "remark": TEST_TAG,
            "now": now,
        },
    )
    conn.execute(
        text("""
            INSERT INTO oa.case_retrieval_task_log (
                retrieval_task_id, case_id, action_type, old_status, new_status,
                content, customer_visible, operator_id, operated_at, status, remark, created_at, updated_at
            )
            VALUES
                (1, 1, 'create', NULL, 'in_progress', '已创建调档任务并分配律师', FALSE, 3, :operated_at, 'active', :remark, :now, :now),
                (2, 2, 'create', NULL, 'in_progress', '已创建调档任务并分配律师', FALSE, 3, :operated_at, 'active', :remark, :now, :now)
            ON CONFLICT DO NOTHING
        """),
        {"operated_at": now, "remark": TEST_TAG, "now": now},
    )
    conn.execute(
        text("""
            INSERT INTO oa.legal_deadline (
                case_id, deadline_title, deadline_type, deadline_time,
                responsible_employee_id, remind_channel, deadline_status, status, remark, created_at, updated_at
            )
            VALUES
                (1, '举证期限', 'evidence', :deadline1, 4, 'system', 'pending', 'active', :remark, :now, :now),
                (2, '答辩期限', 'defense', :deadline2, 4, 'system', 'pending', 'active', :remark, :now, :now)
            ON CONFLICT DO NOTHING
        """),
        {
            "deadline1": datetime(2026, 7, 20, 17, 0, 0),
            "deadline2": datetime(2026, 7, 25, 17, 0, 0),
            "remark": TEST_TAG,
            "now": now,
        },
    )
    print("[seed] Inserted retrievals and deadlines")


def main() -> int:
    try:
        with engine.begin() as conn:
            clean_test_data(conn)
            insert_departments(conn)
            insert_employees(conn)
            insert_parties(conn)
            insert_clients(conn)
            insert_live_and_campaign(conn)
            insert_leads(conn)
            insert_calls_and_appointments(conn)
            insert_negotiations(conn)
            insert_cases(conn)
            insert_financials(conn)
            insert_retrievals_and_deadlines(conn)
        print("[seed] Test data seeded successfully")
        return 0
    except Exception as exc:
        print(f"[seed] ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
