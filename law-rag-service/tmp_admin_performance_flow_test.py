"""
行政绩效部整体流程测试数据。

场景：新建行政绩效部及员工，完成行政资产、行政合同、绩效指标、审批、通知、
      操作日志、数据导出等完整流程验证。

支持重复运行：脚本开头会根据测试员工 ID 清理上次产生的数据。
"""
from datetime import datetime, date, timezone, timedelta
from decimal import Decimal
import json
from sqlalchemy import create_engine, text
from app.core.config import settings

engine = create_engine(settings.database_url_with_search_path, future=True)

now = datetime.now(timezone.utc)
today = date.today()
yesterday = today - timedelta(days=1)
last_month = (today.replace(day=1) - timedelta(days=1)).strftime("%Y-%m")
current_month = today.strftime("%Y-%m")

# ============================================================
# 测试对象 ID（固定分配，避免与已有数据冲突）
# ============================================================
DEPT_ADMIN = 5
DEPT_ADMIN_CODE = "ADMIN"

EMP_ADMIN_STAFF = 10
EMP_ADMIN_MANAGER = 11
EMP_PERFORMANCE_CONFIRM = 12

ROLE_ADMIN_ID = 1
ROLE_ADMIN_CODE = "admin_manager"

USER_ADMIN_STAFF = 1
USER_ADMIN_MANAGER = 2

REGION_CODE = "320000"

TEST_EMPLOYEE_IDS = (EMP_ADMIN_STAFF, EMP_ADMIN_MANAGER, EMP_PERFORMANCE_CONFIRM)


def cleanup(conn):
    """根据测试员工 ID 清理历史测试数据，保证可重复运行。"""
    print("[cleanup] 清理行政绩效部历史测试数据...")

    # 通知表
    conn.execute(text(f"""
        DELETE FROM oa.sys_notification
        WHERE receiver_employee_id IN {TEST_EMPLOYEE_IDS} OR created_by IN {TEST_EMPLOYEE_IDS}
    """))

    # 审批记录表
    conn.execute(text(f"""
        DELETE FROM oa.sys_approval_record
        WHERE applicant_employee_id IN {TEST_EMPLOYEE_IDS} OR approver_employee_id IN {TEST_EMPLOYEE_IDS}
          OR created_by IN {TEST_EMPLOYEE_IDS}
    """))

    # 操作日志表
    conn.execute(text(f"""
        DELETE FROM oa.sys_operation_log
        WHERE operator_id IN {TEST_EMPLOYEE_IDS}
    """))

    # 导出日志表
    conn.execute(text(f"""
        DELETE FROM oa.sys_data_export_log
        WHERE requester_employee_id IN {TEST_EMPLOYEE_IDS}
    """))

    # 绩效指标表
    conn.execute(text(f"""
        DELETE FROM oa.admin_performance_kpi
        WHERE employee_id IN {TEST_EMPLOYEE_IDS} OR department_id = {DEPT_ADMIN}
          OR created_by IN {TEST_EMPLOYEE_IDS} OR confirmed_by IN {TEST_EMPLOYEE_IDS}
    """))

    # 行政资产表
    conn.execute(text(f"""
        DELETE FROM oa.admin_asset
        WHERE keeper_employee_id IN {TEST_EMPLOYEE_IDS} OR created_by IN {TEST_EMPLOYEE_IDS}
    """))

    # 行政合同表（必须先于 sys_attachment 删除，因为 admin_contract 外键引用附件）
    conn.execute(text(f"""
        DELETE FROM oa.admin_contract
        WHERE created_by IN {TEST_EMPLOYEE_IDS}
    """))

    # 附件关联表 & 附件表（通过本次测试的业务类型/员工过滤）
    conn.execute(text(f"""
        DELETE FROM oa.sys_attachment_relation
        WHERE created_by IN {TEST_EMPLOYEE_IDS}
    """))
    conn.execute(text(f"""
        DELETE FROM oa.sys_attachment
        WHERE uploaded_by IN {TEST_EMPLOYEE_IDS}
    """))

    # 用户角色绑定表
    conn.execute(text(f"""
        DELETE FROM oa.sys_user_role
        WHERE employee_id IN {TEST_EMPLOYEE_IDS}
    """))

    # 登录账号表
    conn.execute(text(f"""
        DELETE FROM oa.sys_user
        WHERE employee_id IN {TEST_EMPLOYEE_IDS}
    """))

    # 角色表
    conn.execute(text("DELETE FROM oa.sys_role WHERE id = :role_id"), {"role_id": ROLE_ADMIN_ID})

    # 解除部门与测试员工的循环外键：先清空测试部门的负责人，再删员工，最后删部门
    conn.execute(text("UPDATE oa.sys_department SET manager_employee_id = NULL WHERE id = :dept_id"), {"dept_id": DEPT_ADMIN})

    # 员工表
    conn.execute(text(f"DELETE FROM oa.sys_employee WHERE id IN {TEST_EMPLOYEE_IDS}"))

    # 部门表
    conn.execute(text("DELETE FROM oa.sys_department WHERE id = :dept_id"), {"dept_id": DEPT_ADMIN})

    # 本次测试新增的字典项（按 indicator_code + code_category 精确删除，避免误删其他）
    for indicator_code, code_category, item_value in _TEST_DICT_ITEMS:
        conn.execute(text("""
            DELETE FROM oa.sys_dict_item
            WHERE region_code = :region_code
              AND indicator_code = :indicator_code
              AND code_category = :code_category
              AND item_value = :item_value
        """), {
            "region_code": REGION_CODE,
            "indicator_code": indicator_code,
            "code_category": code_category,
            "item_value": item_value,
        })

    # 清理本次新增的字典类别（如果没有被其他字典项引用）
    for indicator_code, code_category, _ in _TEST_DICT_ITEMS:
        remaining = conn.execute(text("""
            SELECT COUNT(*) FROM oa.sys_dict_item
            WHERE region_code = :region_code
              AND indicator_code = :indicator_code
              AND code_category = :code_category
        """), {
            "region_code": REGION_CODE,
            "indicator_code": indicator_code,
            "code_category": code_category,
        }).scalar()
        if remaining == 0:
            conn.execute(text("""
                DELETE FROM oa.sys_dict_type
                WHERE region_code = :region_code
                  AND indicator_code = :indicator_code
                  AND code_category = :code_category
            """), {
                "region_code": REGION_CODE,
                "indicator_code": indicator_code,
                "code_category": code_category,
            })

    print("[cleanup] 完成。")


# ============================================================
# 本次测试需要补充的字典项
# ============================================================
_TEST_DICT_ITEMS = [
    # (indicator_code, code_category, item_value)
    ("approval_type", "approval_type", "contract_approval"),
    ("approval_status", "approval_status", "pending"),
    ("approval_status", "approval_status", "approved"),
    ("approval_status", "approval_status", "rejected"),
    ("asset_category", "asset_category", "electronic_equipment"),
    ("asset_category", "asset_category", "furniture"),
    ("asset_category", "asset_category", "vehicle"),
    ("asset_status", "asset_status", "in_use"),
    ("asset_status", "asset_status", "under_repair"),
    ("asset_status", "asset_status", "scrapped"),
    ("contract_type", "contract_type", "entrust_agency"),
    ("contract_type", "contract_type", "service_agreement"),
    ("contract_type", "contract_type", "lease"),
    ("kpi_type", "kpi_type", "admin_efficiency"),
    ("kpi_type", "kpi_type", "cost_control"),
    ("kpi_type", "kpi_type", "service_quality"),
    ("notify_channel", "notify_channel", "system"),
    ("notify_status", "notify_status", "pending"),
    ("notify_status", "notify_status", "sent"),
    ("notify_status", "notify_status", "read"),
    ("operation_type", "operation_type", "insert"),
    ("operation_type", "operation_type", "update"),
    ("operation_type", "operation_type", "delete"),
]


def ensure_dict_items(conn):
    """幂等补充行政绩效部测试所需的字典类型和字典项。"""
    print("[dict] 补充行政绩效部测试字典...")

    dict_type_map = {
        "approval_type": ("approval_type", "审批类型", "admin"),
        "approval_status": ("approval_status", "审批状态", "admin"),
        "asset_category": ("asset_category", "资产类别", "admin"),
        "asset_status": ("asset_status", "资产状态", "admin"),
        "contract_type": ("contract_type", "合同类型", "admin"),
        "kpi_type": ("kpi_type", "绩效类型", "admin"),
        "notify_channel": ("notify_channel", "通知渠道", "system"),
        "notify_status": ("notify_status", "通知状态", "system"),
        "operation_type": ("operation_type", "操作类型", "system"),
    }

    dict_item_labels = {
        ("approval_type", "contract_approval"): "行政合同审批",
        ("approval_status", "pending"): "待审批",
        ("approval_status", "approved"): "已通过",
        ("approval_status", "rejected"): "已驳回",
        ("asset_category", "electronic_equipment"): "电子设备",
        ("asset_category", "furniture"): "办公家具",
        ("asset_category", "vehicle"): "车辆",
        ("asset_status", "in_use"): "在用",
        ("asset_status", "under_repair"): "维修中",
        ("asset_status", "scrapped"): "已报废",
        ("contract_type", "entrust_agency"): "委托代理",
        ("contract_type", "service_agreement"): "服务协议",
        ("contract_type", "lease"): "租赁合同",
        ("kpi_type", "admin_efficiency"): "行政效率",
        ("kpi_type", "cost_control"): "成本控制",
        ("kpi_type", "service_quality"): "服务质量",
        ("notify_channel", "system"): "系统消息",
        ("notify_status", "pending"): "待发送",
        ("notify_status", "sent"): "已发送",
        ("notify_status", "read"): "已读",
        ("operation_type", "insert"): "新增",
        ("operation_type", "update"): "修改",
        ("operation_type", "delete"): "删除",
    }

    type_ids = {}
    for indicator_code, (code_category, category_name, module_name) in dict_type_map.items():
        existing = conn.execute(text("""
            SELECT id FROM oa.sys_dict_type
            WHERE region_code = :region_code AND code_category = :code_category
        """), {"region_code": REGION_CODE, "code_category": code_category}).scalar()
        if existing:
            type_ids[code_category] = existing
        else:
            type_id = conn.execute(text("""
                INSERT INTO oa.sys_dict_type (
                    region_code, indicator_code, code_category, category_name,
                    module_name, sort_order, valid_flag, created_at, updated_at, status
                ) VALUES (
                    :region_code, :indicator_code, :code_category, :category_name,
                    :module_name, 0, TRUE, :now, :now, 'active'
                ) RETURNING id
            """), {
                "region_code": REGION_CODE,
                "indicator_code": indicator_code,
                "code_category": code_category,
                "category_name": category_name,
                "module_name": module_name,
                "now": now,
            }).scalar()
            type_ids[code_category] = type_id

    for indicator_code, code_category, item_value in _TEST_DICT_ITEMS:
        existing = conn.execute(text("""
            SELECT id FROM oa.sys_dict_item
            WHERE region_code = :region_code
              AND code_category = :code_category
              AND item_value = :item_value
        """), {
            "region_code": REGION_CODE,
            "code_category": code_category,
            "item_value": item_value,
        }).scalar()
        if existing:
            continue

        label = dict_item_labels.get((code_category, item_value), item_value)
        conn.execute(text("""
            INSERT INTO oa.sys_dict_item (
                dict_type_id, region_code, indicator_code, code_category,
                item_value, item_label, sort_order, valid_flag,
                created_at, created_by, updated_at, updated_by, status
            ) VALUES (
                :dict_type_id, :region_code, :indicator_code, :code_category,
                :item_value, :item_label, 0, TRUE,
                :now, :created_by, :now, :created_by, 'active'
            )
        """), {
            "dict_type_id": type_ids[code_category],
            "region_code": REGION_CODE,
            "indicator_code": indicator_code,
            "code_category": code_category,
            "item_value": item_value,
            "item_label": label,
            "created_by": EMP_ADMIN_MANAGER,
            "now": now,
        })

    print("[dict] 字典补充完成。")


def create_department_and_employees(conn):
    """创建行政绩效部及 3 名员工。"""
    print("[base] 创建行政绩效部及员工...")

    # 1. 先创建员工（部门 ID 暂时为空，避免循环外键依赖）
    employees = [
        (EMP_ADMIN_STAFF, "AD-2024-001", "陈小行", "admin_specialist", "行政专员"),
        (EMP_ADMIN_MANAGER, "AD-2024-002", "刘主管", "admin_manager", "行政主管"),
        (EMP_PERFORMANCE_CONFIRM, "AD-2024-003", "赵绩效", "performance_specialist", "绩效专员"),
    ]
    for emp_id, emp_no, real_name, position, position_name in employees:
        conn.execute(text("""
            INSERT INTO oa.sys_employee (
                id, employee_no, real_name, gender, department_id,
                position_name, employment_status, join_date,
                created_at, created_by, updated_at, updated_by, status
            ) VALUES (
                :emp_id, :emp_no, :real_name, 'unknown', NULL,
                :position_name, 'active', :join_date,
                :now, :created_by, :now, :created_by, 'active'
            )
        """), {
            "emp_id": emp_id,
            "emp_no": emp_no,
            "real_name": real_name,
            "position_name": position_name,
            "join_date": yesterday,
            "created_by": EMP_ADMIN_MANAGER,
            "now": now,
        })

    # 2. 创建部门，指定负责人为行政主管
    conn.execute(text("""
        INSERT INTO oa.sys_department (
            id, department_code, department_name, department_type,
            manager_employee_id, duty_scope, sort_order, created_at, updated_at, status
        ) VALUES (
            :dept_id, :dept_code, '行政绩效部', 'functional',
            :manager_id, '负责律所行政事务、资产管理、合同管理及绩效考核。', 4,
            :now, :now, 'active'
        )
    """), {
        "dept_id": DEPT_ADMIN,
        "dept_code": DEPT_ADMIN_CODE,
        "manager_id": EMP_ADMIN_MANAGER,
        "now": now,
    })

    # 3. 更新员工所属部门
    conn.execute(text(f"""
        UPDATE oa.sys_employee
        SET department_id = {DEPT_ADMIN}, updated_at = :now, updated_by = :updated_by
        WHERE id IN {TEST_EMPLOYEE_IDS}
    """), {"now": now, "updated_by": EMP_ADMIN_MANAGER})

    # 4. 创建角色
    conn.execute(text("""
        INSERT INTO oa.sys_role (
            id, role_code, role_name, data_scope,
            permission_json, created_at, created_by, updated_at, updated_by, status
        ) VALUES (
            :role_id, :role_code, '行政绩效管理员', 'department',
            '{"menus": ["admin_asset", "admin_contract", "admin_performance_kpi"]}',
            :now, :created_by, :now, :created_by, 'active'
        )
    """), {
        "role_id": ROLE_ADMIN_ID,
        "role_code": ROLE_ADMIN_CODE,
        "created_by": EMP_ADMIN_MANAGER,
        "now": now,
    })

    # 5. 创建登录账号
    conn.execute(text("""
        INSERT INTO oa.sys_user (
            id, username, password_hash, employee_id, account_status,
            last_login_at, created_at, created_by, updated_at, updated_by, status
        ) VALUES
            (:u1, 'admin_staff', 'hashed_password_staff', :emp_staff, 'active', :now, :now, :created_by, :now, :created_by, 'active'),
            (:u2, 'admin_manager', 'hashed_password_manager', :emp_manager, 'active', :now, :now, :created_by, :now, :created_by, 'active')
    """), {
        "u1": USER_ADMIN_STAFF,
        "u2": USER_ADMIN_MANAGER,
        "emp_staff": EMP_ADMIN_STAFF,
        "emp_manager": EMP_ADMIN_MANAGER,
        "created_by": EMP_ADMIN_MANAGER,
        "now": now,
    })

    # 6. 用户角色绑定
    conn.execute(text("""
        INSERT INTO oa.sys_user_role (employee_id, user_id, role_id, created_at, created_by, updated_at, updated_by, status)
        VALUES
            (:emp_staff, :u1, :role_id, :now, :created_by, :now, :created_by, 'active'),
            (:emp_manager, :u2, :role_id, :now, :created_by, :now, :created_by, 'active')
    """), {
        "emp_staff": EMP_ADMIN_STAFF,
        "u1": USER_ADMIN_STAFF,
        "emp_manager": EMP_ADMIN_MANAGER,
        "u2": USER_ADMIN_MANAGER,
        "role_id": ROLE_ADMIN_ID,
        "created_by": EMP_ADMIN_MANAGER,
        "now": now,
    })

    print("[base] 部门、员工、角色、账号创建完成。")


def test_admin_asset(conn):
    """行政资产全生命周期测试。"""
    print("[asset] 行政资产流程...")

    # 1. 资产登记（电子设备）
    asset_id = conn.execute(text("""
        INSERT INTO oa.admin_asset (
            asset_no, asset_name, asset_category, brand_model, purchase_date,
            purchase_amount, keeper_employee_id, location, asset_status,
            created_at, created_by, updated_at, updated_by, status, remark
        ) VALUES (
            'ZC-20260709-001', 'ThinkPad X1 笔记本', 'electronic_equipment', '联想 ThinkPad X1',
            :purchase_date, 8999.00, :keeper_id, 'A座301行政办公室', 'in_use',
            :now, :created_by, :now, :created_by, 'active', '分配给行政专员日常使用'
        ) RETURNING id
    """), {
        "purchase_date": yesterday,
        "keeper_id": EMP_ADMIN_STAFF,
        "created_by": EMP_ADMIN_STAFF,
        "now": now,
    }).scalar()

    # 2. 资产变更位置
    conn.execute(text("""
        UPDATE oa.admin_asset
        SET location = 'A座302会议室', updated_at = :now, updated_by = :updated_by
        WHERE id = :asset_id
    """), {"asset_id": asset_id, "updated_by": EMP_ADMIN_STAFF, "now": now})

    # 3. 资产报修
    conn.execute(text("""
        UPDATE oa.admin_asset
        SET asset_status = 'under_repair', remark = '屏幕出现亮点，已送修。',
            updated_at = :now, updated_by = :updated_by
        WHERE id = :asset_id
    """), {"asset_id": asset_id, "updated_by": EMP_ADMIN_MANAGER, "now": now})

    # 4. 资产报废
    conn.execute(text("""
        UPDATE oa.admin_asset
        SET asset_status = 'scrapped', status = 'disabled',
            remark = '设备已过保且维修成本过高，予以报废。',
            updated_at = :now, updated_by = :updated_by
        WHERE id = :asset_id
    """), {"asset_id": asset_id, "updated_by": EMP_ADMIN_MANAGER, "now": now})

    # 5. 记录操作日志
    conn.execute(text("""
        INSERT INTO oa.sys_operation_log (
            operator_id, operator_name, operation_type, biz_type, biz_id,
            operation_content, before_data, after_data,
            ip_address, device_info, created_at, updated_at
        ) VALUES (
            :operator_id, :operator_name, 'update', 'admin_asset', :asset_id,
            '行政资产状态由在用变更为已报废',
            '{"asset_status": "in_use"}'::jsonb,
            '{"asset_status": "scrapped"}'::jsonb,
            '192.168.1.100', 'Windows/Chrome', :now, :now
        )
    """), {
        "operator_id": EMP_ADMIN_MANAGER,
        "operator_name": "刘主管",
        "asset_id": asset_id,
        "now": now,
    })

    # 6. 资产盘点导出
    conn.execute(text("""
        INSERT INTO oa.sys_data_export_log (
            requester_employee_id, module_name, export_reason,
            filter_summary, exported_row_count, export_file_path,
            approved_by, exported_at, created_at, created_by, updated_at, updated_by, status
        ) VALUES (
            :requester_id, '行政资产管理', '月度资产盘点',
            CAST(:filter_summary AS JSONB),
            1, '/exports/admin_asset_20260709.xlsx',
            :approved_by, :now, :now, :created_by, :now, :created_by, 'active'
        )
    """), {
        "requester_id": EMP_ADMIN_STAFF,
        "filter_summary": json.dumps({"asset_status": "all", "department_id": DEPT_ADMIN}),
        "approved_by": EMP_ADMIN_MANAGER,
        "created_by": EMP_ADMIN_STAFF,
        "now": now,
    })

    print(f"[asset] 资产流程完成，asset_id={asset_id}")
    return asset_id


def test_admin_contract(conn):
    """行政合同管理 + 审批 + 通知全流程测试。"""
    print("[contract] 行政合同流程...")

    # 1. 合同登记
    contract_id = conn.execute(text("""
        INSERT INTO oa.admin_contract (
            contract_no, contract_title, contract_type, counterparty_name, amount,
            created_at, created_by, updated_at, updated_by, remark
        ) VALUES (
            'HT-20260709-001', '2026 年度办公耗材集中采购协议', 'service_agreement',
            '连云港市XX办公用品有限公司', 50000.00,
            :now, :created_by, :now, :created_by, '行政专员陈小行起草'
        ) RETURNING id
    """), {"created_by": EMP_ADMIN_STAFF, "now": now}).scalar()

    # 2. 附件上传（模拟）
    attachment_id = conn.execute(text("""
        INSERT INTO oa.sys_attachment (
            biz_type, biz_id, file_name, file_ext, mime_type, file_size,
            storage_type, storage_path, uploaded_by, uploaded_at,
            created_at, created_by, updated_at, updated_by, status,
            file_exists_flag, ai_index_status
        ) VALUES (
            'admin_contract', :contract_id, '办公耗材协议.pdf', 'pdf', 'application/pdf',
            1024000, 'nas', '/nas/admin_contract/HT-20260709-001/办公耗材协议.pdf',
            :uploaded_by, :now, :now, :uploaded_by, :now, :uploaded_by, 'active',
            '1', '1'
        ) RETURNING id
    """), {"contract_id": contract_id, "uploaded_by": EMP_ADMIN_STAFF, "now": now}).scalar()

    conn.execute(text("""
        UPDATE oa.admin_contract
        SET attachment_id = :attachment_id, updated_at = :now, updated_by = :updated_by
        WHERE id = :contract_id
    """), {"contract_id": contract_id, "attachment_id": attachment_id, "updated_by": EMP_ADMIN_STAFF, "now": now})

    conn.execute(text("""
        INSERT INTO oa.sys_attachment_relation (
            attachment_id, entity_type, entity_id, file_usage, sort_order,
            is_primary, created_by, created_at, updated_at, updated_by, remark
        ) VALUES (
            :attachment_id, 'admin_contract', :contract_id, 1, 1,
            1, :created_by, :now, :now, :created_by, '行政合同主附件'
        )
    """), {"attachment_id": attachment_id, "contract_id": contract_id, "created_by": EMP_ADMIN_STAFF, "now": now})

    # 3. 发起审批
    approval_id = conn.execute(text("""
        INSERT INTO oa.sys_approval_record (
            approval_no, approval_type, applicant_employee_id, approver_employee_id,
            approval_opinion, approval_status, created_at, created_by,
            updated_at, updated_by, status, remark
        ) VALUES (
            'SP-20260709-001', 'contract_approval', :applicant_id, :approver_id,
            '协议金额、付款节点、违约责任已复核，符合律所采购制度。', 'approved',
            :now, :applicant_id, :now, :approver_id, 'active', '办公耗材采购协议审批'
        ) RETURNING id
    """), {
        "applicant_id": EMP_ADMIN_STAFF,
        "approver_id": EMP_ADMIN_MANAGER,
        "now": now,
    }).scalar()

    # 4. 发送审批结果通知
    conn.execute(text("""
        INSERT INTO oa.sys_notification (
            receiver_employee_id, biz_type, biz_id, title, content,
            notify_channel, scheduled_time, sent_time, notify_status,
            created_at, created_by, updated_at, updated_by, status
        ) VALUES (
            :receiver_id, 'admin_contract', :contract_id,
            '行政合同审批已通过', '您提交的《2026 年度办公耗材集中采购协议》已通过刘主管审批。',
            'system', :now, :now, 'sent',
            :now, :created_by, :now, :created_by, 'active'
        )
    """), {
        "receiver_id": EMP_ADMIN_STAFF,
        "contract_id": contract_id,
        "created_by": EMP_ADMIN_MANAGER,
        "now": now,
    })

    # 5. 审批通过后更新合同状态（操作日志）
    conn.execute(text("""
        INSERT INTO oa.sys_operation_log (
            operator_id, operator_name, operation_type, biz_type, biz_id,
            operation_content, before_data, after_data,
            ip_address, device_info, created_at, updated_at
        ) VALUES (
            :operator_id, :operator_name, 'update', 'admin_contract', :contract_id,
            '行政合同完成审批，状态更新为已生效',
            '{"approval_status": "pending"}'::jsonb,
            '{"approval_status": "approved"}'::jsonb,
            '192.168.1.101', 'Windows/Chrome', :now, :now
        )
    """), {
        "operator_id": EMP_ADMIN_MANAGER,
        "operator_name": "刘主管",
        "contract_id": contract_id,
        "now": now,
    })

    print(f"[contract] 合同流程完成，contract_id={contract_id}, approval_id={approval_id}")
    return contract_id, approval_id


def test_admin_performance_kpi(conn):
    """绩效指标管理全流程测试。"""
    print("[kpi] 绩效指标流程...")

    kpi_data = [
        (EMP_ADMIN_STAFF, "admin_efficiency", Decimal("95.00"), Decimal("92.50"), Decimal("95.00")),
        (EMP_ADMIN_STAFF, "cost_control", Decimal("10000.00"), Decimal("9500.00"), Decimal("98.00")),
        (EMP_ADMIN_MANAGER, "service_quality", Decimal("90.00"), Decimal("88.00"), Decimal("90.00")),
    ]

    kpi_ids = []
    for emp_id, kpi_type, target_value, actual_value, score in kpi_data:
        kpi_id = conn.execute(text("""
            INSERT INTO oa.admin_performance_kpi (
                employee_id, department_id, period_month, kpi_type,
                target_value, actual_value, score, evaluation_note,
                confirmed_by, created_at, created_by, updated_at, updated_by, status, remark
            ) VALUES (
                :emp_id, :dept_id, :period_month, :kpi_type,
                :target_value, :actual_value, :score, :evaluation_note,
                :confirmed_by, :now, :created_by, :now, :created_by, 'active', :remark
            ) RETURNING id
        """), {
            "emp_id": emp_id,
            "dept_id": DEPT_ADMIN,
            "period_month": current_month,
            "kpi_type": kpi_type,
            "target_value": target_value,
            "actual_value": actual_value,
            "score": score,
            "evaluation_note": '月度绩效考核结果',
            "confirmed_by": EMP_PERFORMANCE_CONFIRM,
            "created_by": EMP_PERFORMANCE_CONFIRM,
            "now": now,
            "remark": '行政绩效部月度 KPI',
        }).scalar()
        kpi_ids.append(kpi_id)

    # 发送 KPI 确认通知
    for emp_id in (EMP_ADMIN_STAFF, EMP_ADMIN_MANAGER):
        conn.execute(text("""
            INSERT INTO oa.sys_notification (
                receiver_employee_id, biz_type, biz_id, title, content,
                notify_channel, scheduled_time, sent_time, notify_status,
                created_at, created_by, updated_at, updated_by, status
            ) VALUES (
                :receiver_id, 'admin_performance_kpi', NULL,
                '月度绩效结果已确认', :content,
                'system', :now, :now, 'sent',
                :now, :created_by, :now, :created_by, 'active'
            )
        """), {
            "receiver_id": emp_id,
            "content": f'您的 {current_month} 月度绩效结果已确认，请登录系统查看详情。',
            "created_by": EMP_PERFORMANCE_CONFIRM,
            "now": now,
        })

    # 绩效数据导出
    conn.execute(text("""
        INSERT INTO oa.sys_data_export_log (
            requester_employee_id, module_name, export_reason,
            filter_summary, exported_row_count, export_file_path,
            approved_by, exported_at, created_at, created_by, updated_at, updated_by, status
        ) VALUES (
            :requester_id, '绩效指标管理', '月度绩效结果导出',
            CAST(:filter_summary AS JSONB),
            3, '/exports/admin_performance_kpi_20260709.xlsx',
            :approved_by, :now, :now, :created_by, :now, :created_by, 'active'
        )
    """), {
        "requester_id": EMP_PERFORMANCE_CONFIRM,
        "filter_summary": json.dumps({"period_month": current_month, "department_id": DEPT_ADMIN}),
        "approved_by": EMP_ADMIN_MANAGER,
        "created_by": EMP_PERFORMANCE_CONFIRM,
        "now": now,
    })

    print(f"[kpi] 绩效流程完成，kpi_ids={kpi_ids}")
    return kpi_ids


def validate_results(conn):
    """简单统计验证。"""
    print("[validate] 结果校验...")

    checks = [
        ("行政绩效部", f"SELECT COUNT(*) FROM oa.sys_department WHERE id = {DEPT_ADMIN}"),
        ("行政员工", f"SELECT COUNT(*) FROM oa.sys_employee WHERE department_id = {DEPT_ADMIN}"),
        ("行政资产", f"SELECT COUNT(*) FROM oa.admin_asset WHERE created_by IN {TEST_EMPLOYEE_IDS}"),
        ("行政合同", f"SELECT COUNT(*) FROM oa.admin_contract WHERE created_by IN {TEST_EMPLOYEE_IDS}"),
        ("绩效指标", f"SELECT COUNT(*) FROM oa.admin_performance_kpi WHERE department_id = {DEPT_ADMIN}"),
        ("审批记录", f"SELECT COUNT(*) FROM oa.sys_approval_record WHERE approval_type = 'contract_approval' AND applicant_employee_id IN {TEST_EMPLOYEE_IDS}"),
        ("通知记录", f"SELECT COUNT(*) FROM oa.sys_notification WHERE created_by IN {TEST_EMPLOYEE_IDS}"),
        ("操作日志", f"SELECT COUNT(*) FROM oa.sys_operation_log WHERE operator_id IN {TEST_EMPLOYEE_IDS}"),
        ("导出日志", f"SELECT COUNT(*) FROM oa.sys_data_export_log WHERE requester_employee_id IN {TEST_EMPLOYEE_IDS}"),
    ]

    for name, sql in checks:
        cnt = conn.execute(text(sql)).scalar()
        print(f"  [{name}] {cnt}")


def main():
    print("=" * 60)
    print("行政绩效部整体流程测试开始")
    print("=" * 60)

    with engine.begin() as conn:
        cleanup(conn)
        ensure_dict_items(conn)
        create_department_and_employees(conn)
        asset_id = test_admin_asset(conn)
        contract_id, approval_id = test_admin_contract(conn)
        kpi_ids = test_admin_performance_kpi(conn)
        validate_results(conn)

    print("=" * 60)
    print("行政绩效部整体流程测试完成")
    print(f"  行政绩效部 department_id={DEPT_ADMIN}")
    print(f"  行政资产 asset_id={asset_id}")
    print(f"  行政合同 contract_id={contract_id}, approval_id={approval_id}")
    print(f"  绩效指标 kpi_ids={kpi_ids}")
    print("=" * 60)


if __name__ == "__main__":
    main()
