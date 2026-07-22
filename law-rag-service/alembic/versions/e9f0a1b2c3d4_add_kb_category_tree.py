"""add arbitrary-depth knowledge category tree

Revision ID: e9f0a1b2c3d4
Revises: d8e9f0a1b2c3
Create Date: 2026-07-17 10:00:00
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "e9f0a1b2c3d4"
down_revision = "d8e9f0a1b2c3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "kb_category",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("category_code", sa.String(80), nullable=False),
        sa.Column("category_name", sa.String(120), nullable=False),
        sa.Column(
            "aliases",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("parent_id", sa.BigInteger(), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("assignable", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("sensitive", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_system", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("created_by", sa.BigInteger(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_by", sa.BigInteger(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="active"),
        sa.Column("remark", sa.String(500), nullable=True),
        sa.ForeignKeyConstraint(
            ["parent_id"],
            ["oa.kb_category.id"],
            name="fk_kb_category_parent",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "parent_id IS NULL OR parent_id <> id",
            name="ck_kb_category_not_self_parent",
        ),
        schema="oa",
    )
    op.create_index(
        "uk_kb_category_code",
        "kb_category",
        ["category_code"],
        unique=True,
        schema="oa",
    )
    op.create_index(
        "ix_kb_category_parent_order",
        "kb_category",
        ["parent_id", "sort_order", "id"],
        schema="oa",
    )
    op.create_index(
        "ix_kb_category_active",
        "kb_category",
        ["status"],
        schema="oa",
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.execute(
        """
        CREATE UNIQUE INDEX uk_kb_category_active_sibling_name
        ON oa.kb_category (COALESCE(parent_id, 0), lower(category_name))
        WHERE deleted_at IS NULL AND status = 'active'
        """
    )

    op.execute(
        """
        INSERT INTO oa.kb_category (
            category_code, category_name, aliases, parent_id, sort_order,
            assignable, sensitive, is_system, status
        ) VALUES
            ('legal', '法律法规', '[]'::jsonb, NULL, 10, FALSE, FALSE, FALSE, 'active'),
            ('client_material', '当事人案件材料', '[]'::jsonb, NULL, 20, FALSE, TRUE, FALSE, 'active'),
            ('firm_material', '律所工作资料', '[]'::jsonb, NULL, 30, FALSE, FALSE, FALSE, 'active'),
            ('client_judgment', '当事人判决案例', '[]'::jsonb, NULL, 40, TRUE, TRUE, FALSE, 'active'),
            ('uncategorized', '待分类', '[]'::jsonb, NULL, 999, FALSE, FALSE, TRUE, 'active')
        """
    )
    op.execute(
        """
        INSERT INTO oa.kb_category (
            category_code, category_name, aliases, parent_id, sort_order,
            assignable, sensitive, is_system, status
        )
        SELECT child.code, child.name, child.aliases::jsonb, parent.id,
               child.sort_order, TRUE, FALSE, FALSE, 'active'
        FROM (VALUES
            ('legal_constitution', '宪法', '[]', 'legal', 10),
            ('legal_law', '法律', '[]', 'legal', 20),
            ('legal_judicial_interpretation', '司法解释', '[]', 'legal', 30),
            ('legal_normative_document', '规范文件', '[]', 'legal', 40),
            ('client_material_open', '未结案', '[]', 'client_material', 10),
            ('client_material_closed', '已结案', '[]', 'client_material', 20),
            ('firm_staffing', '人员配置', '[]', 'firm_material', 10),
            ('firm_operations', '运营部', '[]', 'firm_material', 20),
            ('firm_new_media', '新媒体', '[]', 'firm_material', 30),
            ('firm_marketing', '市场拓展部', '["销转部"]', 'firm_material', 40),
            ('firm_case_management', '案件管理部', '["案管部"]', 'firm_material', 50),
            ('firm_technology', '技术部', '[]', 'firm_material', 60),
            ('firm_management', '管理部', '[]', 'firm_material', 70)
        ) AS child(code, name, aliases, parent_code, sort_order)
        JOIN oa.kb_category parent ON parent.category_code = child.parent_code
        """
    )

    op.add_column(
        "kb_document",
        sa.Column("category_id", sa.BigInteger(), nullable=True),
        schema="oa",
    )
    op.execute(
        """
        UPDATE oa.kb_document AS document
        SET category_id = category.id
        FROM oa.kb_category AS category
        WHERE category.category_code = CASE
            WHEN document.legal_category = '法规' THEN 'legal_law'
            WHEN document.legal_category = '案例' THEN 'client_judgment'
            ELSE 'uncategorized'
        END
        """
    )
    op.alter_column("kb_document", "category_id", nullable=False, schema="oa")
    op.create_foreign_key(
        "fk_kb_document_category",
        "kb_document",
        "kb_category",
        ["category_id"],
        ["id"],
        source_schema="oa",
        referent_schema="oa",
        ondelete="RESTRICT",
    )
    op.create_index(
        "ix_kb_document_category_id",
        "kb_document",
        ["category_id"],
        schema="oa",
    )


def downgrade() -> None:
    op.drop_index("ix_kb_document_category_id", table_name="kb_document", schema="oa")
    op.drop_constraint(
        "fk_kb_document_category", "kb_document", schema="oa", type_="foreignkey"
    )
    op.drop_column("kb_document", "category_id", schema="oa")
    op.drop_index("uk_kb_category_active_sibling_name", table_name="kb_category", schema="oa")
    op.drop_index("ix_kb_category_active", table_name="kb_category", schema="oa")
    op.drop_index("ix_kb_category_parent_order", table_name="kb_category", schema="oa")
    op.drop_index("uk_kb_category_code", table_name="kb_category", schema="oa")
    op.drop_table("kb_category", schema="oa")
