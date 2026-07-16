"""
运营部整体流程测试数据。
场景：视频号直播 + 抖音本地推双渠道获客，验证运营素材、投放计划、广告日消耗、
      直播场次、线索归因与运营统计视图的完整闭环。
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

# 测试数据编号前缀，用于幂等清理
PREFIX = "OPS20260709"

# 固定业务常量
PLATFORM_DOUYIN = 1       # 抖音
PLATFORM_VIDEO = 2        # 视频号
SOURCE_LIVE = 1           # 直播间
SOURCE_AD = 2             # 本地推
ASSET_SCRIPT = 1          # 直播脚本
ASSET_SHORT = 2           # 短视频
INTERACTION_COMMENT = 1   # 评论
INTERACTION_PRIVATE = 2   # 私信
LEGAL_TOPIC_MARRIAGE = 1  # 婚姻家事
LEGAL_TOPIC_DEBT = 3      # 债权债务


def reset_sequence(conn, table_name):
    """重置自增主键序列，避免手动清理后插入冲突。"""
    conn.execute(text(f"""
        SELECT setval(
            pg_get_serial_sequence('oa.{table_name}', 'id'),
            COALESCE((SELECT MAX(id) FROM oa.{table_name}), 1)
        )
    """))


def get_or_create_operation_department(conn):
    """获取或创建运营部。"""
    dept_id = conn.execute(text("""
        SELECT id FROM oa.sys_department
        WHERE department_code = 'OPS' AND deleted_at IS NULL
    """)).scalar()
    if dept_id:
        return dept_id

    reset_sequence(conn, "sys_department")

    dept_id = conn.execute(text("""
        INSERT INTO oa.sys_department (
            department_code, department_name, department_type,
            parent_department_id, sort_order,
            created_at, updated_at, status
        ) VALUES (
            'OPS', '运营部', 'business',
            NULL, 4,
            :now, :now, 'active'
        )
        RETURNING id
    """), {"now": now}).scalar()
    return dept_id


def get_or_create_operation_employee(conn, dept_id):
    """获取或创建运营部测试员工（郑十一）；若被软删除则恢复。"""
    emp = conn.execute(text("""
        SELECT id, deleted_at FROM oa.sys_employee
        WHERE employee_no = 'E011'
        ORDER BY id DESC LIMIT 1
    """)).fetchone()
    if emp:
        emp_id = emp[0]
        if emp[1] is not None:
            conn.execute(text("""
                UPDATE oa.sys_employee
                SET deleted_at = NULL, status = 'active', department_id = :dept_id,
                    updated_at = :now, updated_by = :emp_id
                WHERE id = :id
            """), {"dept_id": dept_id, "now": now, "emp_id": emp_id, "id": emp_id})
        return emp_id

    reset_sequence(conn, "sys_employee")

    emp_id = conn.execute(text("""
        INSERT INTO oa.sys_employee (
            employee_no, real_name, gender, department_id, position_name,
            employment_status, join_date, created_at, updated_at, status
        ) VALUES (
            'E011', '郑十一', 'male', :dept_id, '运营专员',
            'active', :join_date, :now, :now, 'active'
        )
        RETURNING id
    """), {"dept_id": dept_id, "join_date": yesterday, "now": now}).scalar()
    return emp_id


def cleanup_operation_test_data(conn):
    """幂等清理：删除本次运营测试生成的全部数据（硬删除，便于重复运行）。"""
    # 1. 线索来源触点归因
    conn.execute(text("""
        DELETE FROM oa.lead_source_touch
        WHERE lead_id IN (
            SELECT id FROM oa.crm_lead WHERE lead_no LIKE :prefix
        )
    """), {"prefix": f"{PREFIX}%"})

    # 2. 直播线索绑定
    conn.execute(text("""
        DELETE FROM oa.ops_live_lead
        WHERE lead_id IN (
            SELECT id FROM oa.crm_lead WHERE lead_no LIKE :prefix
        )
    """), {"prefix": f"{PREFIX}%"})

    # 3. 广告日消耗
    conn.execute(text("""
        DELETE FROM oa.ops_ad_spend_daily
        WHERE campaign_id IN (
            SELECT id FROM oa.ops_ad_campaign WHERE campaign_no LIKE :prefix
        )
    """), {"prefix": f"{PREFIX}%"})

    # 4. 投流素材
    conn.execute(text("""
        DELETE FROM oa.ops_ad_creative
        WHERE campaign_id IN (
            SELECT id FROM oa.ops_ad_campaign WHERE campaign_no LIKE :prefix
        )
    """), {"prefix": f"{PREFIX}%"})

    # 5. 投流计划
    conn.execute(text("""
        DELETE FROM oa.ops_ad_campaign WHERE campaign_no LIKE :prefix
    """), {"prefix": f"{PREFIX}%"})

    # 6. 直播场次
    conn.execute(text("""
        DELETE FROM oa.ops_live_session WHERE session_no LIKE :prefix
    """), {"prefix": f"{PREFIX}%"})

    # 7. 运营素材
    conn.execute(text("""
        DELETE FROM oa.ops_content_asset
        WHERE asset_title LIKE :prefix
    """), {"prefix": f"{PREFIX}%"})

    # 8. 线索
    conn.execute(text("""
        DELETE FROM oa.crm_lead WHERE lead_no LIKE :prefix
    """), {"prefix": f"{PREFIX}%"})

    # 9. 客户
    conn.execute(text("""
        DELETE FROM oa.crm_client WHERE client_no LIKE :prefix
    """), {"prefix": f"{PREFIX}%"})

    # 10. 当事人
    conn.execute(text("""
        DELETE FROM oa.party_main WHERE party_code LIKE :prefix
    """), {"prefix": f"{PREFIX}%"})

    # 11. 测试员工（软删除，保留审计痕迹）
    conn.execute(text("""
        UPDATE oa.sys_employee
        SET deleted_at = :now, status = 'inactive', updated_at = :now
        WHERE employee_no = 'E011' AND deleted_at IS NULL
    """), {"now": now})


with engine.begin() as conn:
    # ============================================================
    # 0. 幂等清理旧测试数据
    # ============================================================
    cleanup_operation_test_data(conn)

    # ============================================================
    # 1. 准备基础数据：运营部 + 运营专员
    # ============================================================
    dept_ops_id = get_or_create_operation_department(conn)
    emp_ops_id = get_or_create_operation_employee(conn, dept_ops_id)
    print(f"运营部 id={dept_ops_id}, 运营专员郑十一 id={emp_ops_id}")

    # ============================================================
    # 2. 运营素材管理
    # ============================================================
    # 2.1 直播脚本素材
    asset_script_id = conn.execute(text("""
        INSERT INTO oa.ops_content_asset (
            asset_title, asset_type, legal_topic, owner_department_id, creator_employee_id,
            content_summary, publish_platform, publish_time,
            created_at, updated_at, status, created_by, updated_by
        ) VALUES (
            :title, :asset_type, :legal_topic, :dept_id, :emp_id,
            :summary, :platform, :publish_time,
            :now, :now, 'active', :emp_id, :emp_id
        )
        RETURNING id
    """), {
        "title": f"{PREFIX}-婚姻家事直播脚本-7月专场",
        "asset_type": ASSET_SCRIPT,
        "legal_topic": LEGAL_TOPIC_MARRIAGE,
        "dept_id": dept_ops_id,
        "emp_id": emp_ops_id,
        "summary": "围绕离婚财产分割、子女抚养权、彩礼返还等高频问题设计的话术脚本。",
        "platform": "视频号",
        "publish_time": yesterday,
        "now": now
    }).scalar()

    # 2.2 短视频素材
    asset_video_id = conn.execute(text("""
        INSERT INTO oa.ops_content_asset (
            asset_title, asset_type, legal_topic, owner_department_id, creator_employee_id,
            content_summary, publish_platform, publish_time,
            created_at, updated_at, status, created_by, updated_by
        ) VALUES (
            :title, :asset_type, :legal_topic, :dept_id, :emp_id,
            :summary, :platform, :publish_time,
            :now, :now, 'active', :emp_id, :emp_id
        )
        RETURNING id
    """), {
        "title": f"{PREFIX}-债权债务短视频-借条注意事项",
        "asset_type": ASSET_SHORT,
        "legal_topic": LEGAL_TOPIC_DEBT,
        "dept_id": dept_ops_id,
        "emp_id": emp_ops_id,
        "summary": "讲解借条必备要素、诉讼时效、证据留存等知识点，用于抖音本地推投放。",
        "platform": "抖音",
        "publish_time": yesterday,
        "now": now
    }).scalar()

    # ============================================================
    # 3. 投放计划与素材
    # ============================================================
    # 3.1 抖音本地推投放计划
    campaign_id = conn.execute(text("""
        INSERT INTO oa.ops_ad_campaign (
            campaign_no, campaign_name, platform, case_source, campaign_type,
            start_date, end_date, budget_amount, owner_employee_id, campaign_status,
            remark, created_at, updated_at, status
        ) VALUES (
            :campaign_no, :campaign_name, :platform, :case_source, :campaign_type,
            :start_date, :end_date, :budget_amount, :emp_id, 1,
            :remark, :now, :now, 'active'
        )
        RETURNING id
    """), {
        "campaign_no": f"{PREFIX}-CAM-001",
        "campaign_name": "抖音本地推-债权债务专题-7月",
        "platform": PLATFORM_DOUYIN,
        "case_source": SOURCE_AD,
        "campaign_type": 1,
        "start_date": yesterday,
        "end_date": next_week,
        "budget_amount": 15000.00,
        "emp_id": emp_ops_id,
        "remark": "测试投放计划，用于验证运营部投放闭环",
        "now": now
    }).scalar()

    # 3.2 投流素材（关联短视频素材）
    creative_id = conn.execute(text("""
        INSERT INTO oa.ops_ad_creative (
            campaign_id, asset_id, creative_no, creative_name, creative_type, platform,
            publish_url, material_summary, exposure_count, click_count, lead_count,
            ad_cost, creative_status, created_at, updated_at, remark
        ) VALUES (
            :campaign_id, :asset_id, :creative_no, :creative_name, :creative_type, :platform,
            :publish_url, :material_summary, :exposure_count, :click_count, :lead_count,
            :ad_cost, 1, :now, :now, :remark
        )
        RETURNING id
    """), {
        "campaign_id": campaign_id,
        "asset_id": asset_video_id,
        "creative_no": f"{PREFIX}-CRE-001",
        "creative_name": "借条注意事项-短视频创意A",
        "creative_type": ASSET_SHORT,
        "platform": PLATFORM_DOUYIN,
        "publish_url": "https://example.com/ad/ops001",
        "material_summary": "测试投流素材，关联债权债务短视频",
        "exposure_count": 80000,
        "click_count": 4800,
        "lead_count": 260,
        "ad_cost": 4200.00,
        "remark": "测试创意",
        "now": now
    }).scalar()

    # ============================================================
    # 4. 直播场次（必须在广告日消耗前创建，因为日消耗要求关联 live_session_id）
    # ============================================================
    live_session_id = conn.execute(text("""
        INSERT INTO oa.ops_live_session (
            session_no, platform, live_title, legal_topic, comment_count,
            private_message_count, lead_count, conversion_count, ad_cost, data_summary,
            created_at, updated_at, status, remark, online_user_count, lead_conversion_rate,
            exposure_entry_rate, live_group, exposure_count, entry_user_count, valid_viewer_count,
            avg_watch_seconds, valid_lead_count, form_submit_count, private_message_user_count,
            exposure_entry_rate_calc_rule, lead_conversion_rate_calc_rule
        ) VALUES (
            :session_no, :platform, :live_title, :legal_topic, :comment_count,
            :private_message_count, :lead_count, :conversion_count, :ad_cost, :data_summary,
            :now, :now, 'active', :remark, :online_user_count, :lead_conversion_rate,
            :exposure_entry_rate, :live_group, :exposure_count, :entry_user_count, :valid_viewer_count,
            :avg_watch_seconds, :valid_lead_count, :form_submit_count, :private_message_user_count,
            :exposure_entry_rate_calc_rule, :lead_conversion_rate_calc_rule
        )
        RETURNING id
    """), {
        "session_no": f"{PREFIX}-LS-001",
        "platform": "视频号",
        "live_title": "婚姻家事在线答疑-7月专场",
        "legal_topic": LEGAL_TOPIC_MARRIAGE,
        "comment_count": 620,
        "private_message_count": 210,
        "lead_count": 38,
        "conversion_count": 5,
        "ad_cost": Decimal("1500.00"),
        "data_summary": "视频号直播，解答离婚财产分割与子女抚养问题，线索质量较高。",
        "remark": "测试直播场次",
        "online_user_count": 950,
        "lead_conversion_rate": Decimal("0.0400"),
        "exposure_entry_rate": Decimal("0.1400"),
        "live_group": 1,
        "exposure_count": 7000,
        "entry_user_count": 980,
        "valid_viewer_count": 760,
        "avg_watch_seconds": 210,
        "valid_lead_count": 38,
        "form_submit_count": 42,
        "private_message_user_count": 180,
        "exposure_entry_rate_calc_rule": 1,
        "lead_conversion_rate_calc_rule": 1,
        "now": now
    }).scalar()

    # 3.3 广告日消耗（多日），关联到直播场次
    for offset, spend_date in enumerate([yesterday, today]):
        conn.execute(text("""
            INSERT INTO oa.ops_ad_spend_daily (
                campaign_id, creative_id, spend_date, ad_cost, exposure_count, click_count,
                entry_user_count, lead_count, valid_lead_count, deal_amount, received_amount,
                cost_per_lead, roi_rate, created_at, updated_at, remark, live_session_id,
                cumulative_viewer_count, platform_snapshot
            ) VALUES (
                :campaign_id, :creative_id, :spend_date, :ad_cost, :exposure_count, :click_count,
                :entry_user_count, :lead_count, :valid_lead_count, :deal_amount, :received_amount,
                :cost_per_lead, :roi_rate, :now, :now, :remark, :live_session_id,
                :cumulative_viewer_count, :platform_snapshot
            )
        """), {
            "campaign_id": campaign_id,
            "creative_id": creative_id,
            "spend_date": spend_date,
            "ad_cost": Decimal("2200.00") if offset == 0 else Decimal("2000.00"),
            "exposure_count": 40000 if offset == 0 else 36000,
            "click_count": 2400 if offset == 0 else 2200,
            "entry_user_count": 900 if offset == 0 else 800,
            "lead_count": 140 if offset == 0 else 120,
            "valid_lead_count": 90 if offset == 0 else 80,
            "deal_amount": Decimal("0.00"),
            "received_amount": Decimal("0.00"),
            "cost_per_lead": Decimal("15.71") if offset == 0 else Decimal("16.67"),
            "roi_rate": Decimal("0.0000"),
            "remark": f"测试日消耗-{spend_date}",
            "live_session_id": live_session_id,
            "cumulative_viewer_count": 800 if offset == 0 else 750,
            "platform_snapshot": "抖音-本地推",
            "now": now
        })

    # ============================================================
    # 4. 直播场次与线索绑定
    # ============================================================
    # 4.1 创建两个当事人/客户/线索（分别来自广告投放和直播间）
    test_parties = []
    for idx, (name, mobile, id_no, topic, source) in enumerate([
        ("吴十", "13944445555", "320722198001011234", LEGAL_TOPIC_DEBT, SOURCE_AD),
        ("郑十二", "13955556666", "320722199002021234", LEGAL_TOPIC_MARRIAGE, SOURCE_LIVE),
    ]):
        party_code = f"{PREFIX}-P-{idx+1:03d}"
        party_id = conn.execute(text("""
            INSERT INTO oa.party_main (
                party_code, party_type, party_name, gender, mobile, id_type, id_number,
                address, is_repeat_party, party_status, is_deleted, created_at, updated_at,
                first_source
            ) VALUES (
                :party_code, 1, :name, 1, :mobile, 1, :id_no,
                :address, 2, 1, 2, :now, :now,
                :source
            )
            RETURNING id
        """), {
            "party_code": party_code,
            "name": name,
            "mobile": mobile,
            "id_no": id_no,
            "address": "江苏省连云港市海州区",
            "source": source,
            "now": now
        }).scalar()

        client_no = f"{PREFIX}-C-{idx+1:03d}"
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
            "client_no": client_no,
            "id_no": id_no,
            "summary": f"{name}（运营部测试线索当事人）",
            "owner": emp_ops_id,
            "source": source,
            "now": now
        }).scalar()

        lead_no = f"{PREFIX}-L-{idx+1:03d}"
        lead_title = f"{name}-{'本地推' if source == SOURCE_AD else '直播间'}-运营测试线索"
        lead_id = conn.execute(text("""
            INSERT INTO oa.crm_lead (
                client_id, lead_no, lead_title, case_brief, demand_summary, urgency_level, lead_status,
                case_source, owner_employee_id, owner_department_id,
                main_negotiator_id, consultant_employee_id,
                case_type, deal_intention, deal_amount, received_amount, remaining_balance,
                wechat_added_flag, wechat_added_at, wechat_added_by,
                key_case_flag, key_case_reason, is_duplicate_party, assigned_at,
                created_at, updated_at, status
            ) VALUES (
                :client_id, :lead_no, :lead_title, :case_brief, :demand_summary, 'high', 'new',
                :source, :owner, :dept,
                :owner, :owner,
                2, 3, 0.00, 0.00, 0.00,
                1, :yesterday, :owner,
                0, '普通案件', 2, :yesterday,
                :now, :now, 'active'
            )
            RETURNING id
        """), {
            "client_id": client_id,
            "lead_no": lead_no,
            "lead_title": lead_title,
            "case_brief": "运营部测试用线索，用于验证来源归因与转化漏斗统计。",
            "demand_summary": "了解法律咨询流程与委托标准。",
            "source": source,
            "owner": emp_ops_id,
            "dept": dept_ops_id,
            "yesterday": yesterday,
            "now": now
        }).scalar()

        test_parties.append({
            "party_id": party_id,
            "client_id": client_id,
            "lead_id": lead_id,
            "name": name,
            "source": source
        })

    # 4.3 直播线索绑定（仅直播间来源）
    for person in test_parties:
        if person["source"] != SOURCE_LIVE:
            continue
        conn.execute(text("""
            INSERT INTO oa.ops_live_lead (
                live_session_id, lead_id, platform_user_id, interaction_type,
                interaction_content, capture_time, assigned_to_employee_id, processing_status,
                created_at, updated_at, created_by, updated_by
            ) VALUES (
                :live_session_id, :lead_id, :platform_user_id, :interaction_type,
                :interaction_content, :capture_time, :assigned_to, :processing_status,
                :now, :now, :emp_id, :emp_id
            )
        """), {
            "live_session_id": live_session_id,
            "lead_id": person["lead_id"],
            "platform_user_id": f"video_user_{person['lead_id']}",
            "interaction_type": INTERACTION_PRIVATE,
            "interaction_content": "私信咨询离婚财产分割问题，留下手机号预约到所。",
            "capture_time": yesterday,
            "assigned_to": emp_ops_id,
            "processing_status": "2",
            "emp_id": emp_ops_id,
            "now": now
        })

    # 4.4 线索来源触点归因
    for person in test_parties:
        campaign = campaign_id if person["source"] == SOURCE_AD else None
        creative = creative_id if person["source"] == SOURCE_AD else None
        live = live_session_id if person["source"] == SOURCE_LIVE else None
        conn.execute(text("""
            INSERT INTO oa.lead_source_touch (
                lead_id, touch_channel, touch_time, touch_content,
                campaign_id, creative_id, asset_id, source_platform_user_id,
                is_first_touch, is_last_touch, conversion_contribution_amount,
                created_by, updated_at, updated_by, status, remark, created_at
            ) VALUES (
                :lead_id, :channel, :touch_time, :touch_content,
                :campaign, :creative, :asset, :platform_user_id,
                1, 1, :contribution,
                :emp_id, :now, :emp_id, 'active', '首次触点-运营部测试', :now
            )
        """), {
            "lead_id": person["lead_id"],
            "channel": person["source"],
            "touch_time": yesterday,
            "touch_content": "通过抖音本地推短视频留资" if person["source"] == SOURCE_AD else "通过视频号直播间私信留资",
            "campaign": campaign,
            "creative": creative,
            "asset": asset_video_id if person["source"] == SOURCE_AD else asset_script_id,
            "platform_user_id": f"platform_user_{person['lead_id']}",
            "contribution": Decimal("0.00"),
            "emp_id": emp_ops_id,
            "now": now
        })

    # ============================================================
    # 5. 统计视图验证
    # ============================================================
    print("\n运营统计视图验证结果：")

    # 5.1 直播效果视图
    live_effect = conn.execute(text("""
        SELECT session_id, live_date, platform, exposure_count, inquiry_count,
               lead_count, valid_lead_count, appointment_count, deal_count, paid_amount
        FROM oa.v_ops_live_effect
        WHERE session_id = :session_id
    """), {"session_id": live_session_id}).fetchone()
    print(f"v_ops_live_effect: {live_effect}")

    # 5.2 运营渠道日报
    channel_daily = conn.execute(text("""
        SELECT report_date, platform_name, ad_cost, lead_count, cost_per_lead,
               exposure_count, cumulative_viewer_count
        FROM oa.v_ops_channel_daily_report
        WHERE live_session_id = :session_id
        ORDER BY report_date
    """), {"session_id": live_session_id}).fetchall()
    print(f"v_ops_channel_daily_report: {len(channel_daily)} 条")
    for row in channel_daily:
        print(f"  {row}")

    # 5.3 线索转化漏斗（按运营渠道）
    funnel = conn.execute(text("""
        SELECT stat_date, channel_id, channel_name, lead_count, assigned_count
        FROM oa.v_lead_conversion_funnel
        WHERE stat_date = :today AND channel_id IN (:source_ad, :source_live)
    """), {"today": today, "source_ad": SOURCE_AD, "source_live": SOURCE_LIVE}).fetchall()
    print(f"v_lead_conversion_funnel: {len(funnel)} 条")
    for row in funnel:
        print(f"  {row}")

    # ============================================================
    # 6. 结果汇总
    # ============================================================
    print("\n运营部整体流程测试数据插入完成：")
    print(f"  运营部 department_id={dept_ops_id}")
    print(f"  运营专员 employee_id={emp_ops_id}")
    print(f"  直播脚本素材 asset_id={asset_script_id}")
    print(f"  短视频素材 asset_id={asset_video_id}")
    print(f"  投放计划 campaign_id={campaign_id}")
    print(f"  投流素材 creative_id={creative_id}")
    print(f"  直播场次 live_session_id={live_session_id}")
    for person in test_parties:
        print(f"  线索 {person['name']}: lead_id={person['lead_id']}, source={person['source']}")
