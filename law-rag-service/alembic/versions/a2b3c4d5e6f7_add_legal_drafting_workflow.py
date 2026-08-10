"""add_legal_drafting_workflow

Revision ID: a2b3c4d5e6f7
Revises: f1a2b3c4d5e6
Create Date: 2026-07-22 18:00:00

受控多 Agent 法律文书生成：模板版本、任务、版本、来源、审校、人工输入及事件。
LangGraph checkpoint 使用独立 agent_runtime schema；业务状态仍以 oa generation_run 为准。
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "a2b3c4d5e6f7"
down_revision = "f1a2b3c4d5e6"
branch_labels = None
depends_on = None


def _audit_columns() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("created_by", sa.BigInteger(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_by", sa.BigInteger(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
    ]


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS agent_runtime")
    op.add_column("kb_document", sa.Column("effective_status", sa.String(length=20), nullable=False, server_default="active"), schema="oa")
    op.add_column("kb_document", sa.Column("effective_from", sa.Date(), nullable=True), schema="oa")
    op.add_column("kb_document", sa.Column("effective_to", sa.Date(), nullable=True), schema="oa")
    op.add_column("kb_document", sa.Column("cause_codes", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"), schema="oa")
    op.create_index("idx_kb_document_legal_validity", "kb_document", ["effective_status", "effective_from", "effective_to"], schema="oa")

    op.create_table(
        "legal_document_template",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("template_code", sa.String(length=120), nullable=False),
        sa.Column("template_name", sa.String(length=255), nullable=False),
        sa.Column("document_type", sa.String(length=80), nullable=False),
        sa.Column("cause_code", sa.String(length=80), nullable=True),
        sa.Column("cause_name", sa.String(length=160), nullable=True),
        sa.Column("cause_aliases", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
        sa.Column("party_role", sa.String(length=50), nullable=True),
        sa.Column("procedure_stage", sa.String(length=80), nullable=True),
        sa.Column("current_version_id", sa.BigInteger(), nullable=True),
        *_audit_columns(),
        sa.UniqueConstraint("template_code", name="uk_legal_document_template_code"),
        schema="oa",
    )

    op.create_table(
        "legal_document_template_version",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("template_id", sa.BigInteger(), nullable=False),
        sa.Column("version_no", sa.String(length=50), nullable=False),
        sa.Column("source_attachment_id", sa.BigInteger(), nullable=True),
        sa.Column("normalized_attachment_id", sa.BigInteger(), nullable=True),
        sa.Column("source_path", sa.String(length=500), nullable=True),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("file_size", sa.BigInteger(), nullable=False),
        sa.Column("source_format", sa.String(length=20), nullable=False),
        sa.Column("schema_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("render_binding_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("compiler_report_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("parser_version", sa.String(length=80), nullable=False),
        sa.Column("approved_by", sa.BigInteger(), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        *_audit_columns(),
        sa.ForeignKeyConstraint(["template_id"], ["oa.legal_document_template.id"], name="fk_legal_template_version_template"),
        sa.ForeignKeyConstraint(["source_attachment_id"], ["oa.sys_attachment.id"], name="fk_legal_template_version_source_attachment"),
        sa.ForeignKeyConstraint(["normalized_attachment_id"], ["oa.sys_attachment.id"], name="fk_legal_template_version_normalized_attachment"),
        sa.UniqueConstraint("template_id", "version_no", name="uk_legal_template_version_no"),
        schema="oa",
    )
    op.create_foreign_key(
        "fk_legal_template_current_version",
        "legal_document_template",
        "legal_document_template_version",
        ["current_version_id"],
        ["id"],
        source_schema="oa",
        referent_schema="oa",
        ondelete="SET NULL",
    )

    op.create_table(
        "legal_document_generation_run",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("thread_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("idempotency_key", sa.String(length=120), nullable=True),
        sa.Column("case_id", sa.BigInteger(), nullable=False),
        sa.Column("template_version_id", sa.BigInteger(), nullable=True),
        sa.Column("document_type", sa.String(length=80), nullable=False),
        sa.Column("cause_code", sa.String(length=80), nullable=True),
        sa.Column("party_role", sa.String(length=50), nullable=True),
        sa.Column("run_status", sa.String(length=50), nullable=False, server_default="pending"),
        sa.Column("current_node", sa.String(length=100), nullable=True),
        sa.Column("progress", sa.SmallInteger(), nullable=False, server_default="0"),
        sa.Column("selected_material_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
        sa.Column("selected_evidence_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
        sa.Column("allowed_doc_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
        sa.Column("permission_snapshot_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("snapshot_hash", sa.String(length=64), nullable=True),
        sa.Column("model_config_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("prompt_version", sa.String(length=80), nullable=False, server_default="legal-drafting-v1"),
        sa.Column("parser_version", sa.String(length=80), nullable=False, server_default="template-compiler-v1"),
        sa.Column("input_version", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("event_seq", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("lease_owner", sa.String(length=120), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("waiting_reason", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("result_document_id", sa.BigInteger(), nullable=True),
        sa.Column("result_version_id", sa.BigInteger(), nullable=True),
        sa.Column("error_code", sa.String(length=80), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        *_audit_columns(),
        sa.ForeignKeyConstraint(["case_id"], ["oa.case_main.id"], name="fk_legal_generation_run_case"),
        sa.ForeignKeyConstraint(["template_version_id"], ["oa.legal_document_template_version.id"], name="fk_legal_generation_run_template_version"),
        sa.ForeignKeyConstraint(["result_document_id"], ["oa.legal_document.id"], name="fk_legal_generation_run_document"),
        sa.UniqueConstraint("thread_id", name="uk_legal_generation_run_thread"),
        sa.UniqueConstraint("idempotency_key", name="uk_legal_generation_run_idempotency"),
        sa.CheckConstraint("progress >= 0 AND progress <= 100", name="ck_legal_generation_run_progress"),
        schema="oa",
    )

    op.create_table(
        "legal_document_version",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("legal_document_id", sa.BigInteger(), nullable=False),
        sa.Column("generation_run_id", sa.BigInteger(), nullable=True),
        sa.Column("version_no", sa.Integer(), nullable=False),
        sa.Column("version_kind", sa.String(length=30), nullable=False),
        sa.Column("version_status", sa.String(length=50), nullable=False, server_default="draft"),
        sa.Column("structured_content_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("provenance_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("audit_report_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("docx_attachment_id", sa.BigInteger(), nullable=True),
        sa.Column("pdf_attachment_id", sa.BigInteger(), nullable=True),
        sa.Column("approved_by", sa.BigInteger(), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("created_by", sa.BigInteger(), nullable=True),
        sa.ForeignKeyConstraint(["legal_document_id"], ["oa.legal_document.id"], name="fk_legal_document_version_document"),
        sa.ForeignKeyConstraint(["generation_run_id"], ["oa.legal_document_generation_run.id"], name="fk_legal_document_version_run"),
        sa.ForeignKeyConstraint(["docx_attachment_id"], ["oa.sys_attachment.id"], name="fk_legal_document_version_docx"),
        sa.ForeignKeyConstraint(["pdf_attachment_id"], ["oa.sys_attachment.id"], name="fk_legal_document_version_pdf"),
        sa.UniqueConstraint("legal_document_id", "version_no", name="uk_legal_document_version_no"),
        schema="oa",
    )
    op.create_foreign_key(
        "fk_legal_generation_run_result_version",
        "legal_document_generation_run",
        "legal_document_version",
        ["result_version_id"],
        ["id"],
        source_schema="oa",
        referent_schema="oa",
        ondelete="SET NULL",
    )

    op.create_table(
        "legal_document_source",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("version_id", sa.BigInteger(), nullable=False),
        sa.Column("field_id", sa.String(length=160), nullable=True),
        sa.Column("section_id", sa.String(length=120), nullable=True),
        sa.Column("source_type", sa.String(length=40), nullable=False),
        sa.Column("material_id", sa.BigInteger(), nullable=True),
        sa.Column("evidence_id", sa.BigInteger(), nullable=True),
        sa.Column("knowledge_document_id", sa.BigInteger(), nullable=True),
        sa.Column("chunk_id", sa.String(length=160), nullable=True),
        sa.Column("attachment_id", sa.BigInteger(), nullable=True),
        sa.Column("page_no", sa.Integer(), nullable=True),
        sa.Column("paragraph_no", sa.Integer(), nullable=True),
        sa.Column("table_index", sa.Integer(), nullable=True),
        sa.Column("cell_ref", sa.String(length=30), nullable=True),
        sa.Column("quote_text", sa.Text(), nullable=True),
        sa.Column("content_hash", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["version_id"], ["oa.legal_document_version.id"], name="fk_legal_document_source_version", ondelete="CASCADE"),
        schema="oa",
    )

    op.create_table(
        "legal_document_review_issue",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("run_id", sa.BigInteger(), nullable=False),
        sa.Column("version_id", sa.BigInteger(), nullable=True),
        sa.Column("issue_code", sa.String(length=80), nullable=False),
        sa.Column("review_type", sa.String(length=40), nullable=False),
        sa.Column("severity", sa.String(length=20), nullable=False),
        sa.Column("section_id", sa.String(length=120), nullable=True),
        sa.Column("field_id", sa.String(length=160), nullable=True),
        sa.Column("source_refs", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("recommended_action", sa.String(length=120), nullable=True),
        sa.Column("rewrite_target", sa.String(length=160), nullable=True),
        sa.Column("review_round", sa.SmallInteger(), nullable=False, server_default="1"),
        sa.Column("resolution_status", sa.String(length=30), nullable=False, server_default="open"),
        sa.Column("resolved_by", sa.BigInteger(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["run_id"], ["oa.legal_document_generation_run.id"], name="fk_legal_review_issue_run", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["version_id"], ["oa.legal_document_version.id"], name="fk_legal_review_issue_version"),
        schema="oa",
    )

    op.create_table(
        "legal_document_user_input",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("run_id", sa.BigInteger(), nullable=False),
        sa.Column("input_version", sa.Integer(), nullable=False),
        sa.Column("field_id", sa.String(length=160), nullable=False),
        sa.Column("value_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("resolution_type", sa.String(length=30), nullable=False),
        sa.Column("source_note", sa.String(length=500), nullable=True),
        sa.Column("submitted_by", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["run_id"], ["oa.legal_document_generation_run.id"], name="fk_legal_user_input_run", ondelete="CASCADE"),
        sa.UniqueConstraint("run_id", "input_version", "field_id", name="uk_legal_user_input_version_field"),
        schema="oa",
    )

    op.create_table(
        "legal_document_generation_event",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("run_id", sa.BigInteger(), nullable=False),
        sa.Column("event_seq", sa.BigInteger(), nullable=False),
        sa.Column("event_type", sa.String(length=60), nullable=False),
        sa.Column("payload_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["run_id"], ["oa.legal_document_generation_run.id"], name="fk_legal_generation_event_run", ondelete="CASCADE"),
        sa.UniqueConstraint("run_id", "event_seq", name="uk_legal_generation_event_seq"),
        schema="oa",
    )

    for name, table, columns in (
        ("idx_ld_template_match", "legal_document_template", ["document_type", "cause_code", "party_role", "status"]),
        ("idx_ld_template_version_status", "legal_document_template_version", ["template_id", "status"]),
        ("idx_ld_run_queue", "legal_document_generation_run", ["run_status", "created_at"]),
        ("idx_ld_run_case", "legal_document_generation_run", ["case_id", "created_at"]),
        ("idx_ld_run_lease", "legal_document_generation_run", ["lease_expires_at"]),
        ("idx_ld_version_run", "legal_document_version", ["generation_run_id"]),
        ("idx_ld_source_field", "legal_document_source", ["version_id", "field_id"]),
        ("idx_ld_issue_open", "legal_document_review_issue", ["run_id", "resolution_status"]),
    ):
        op.create_index(name, table, columns, schema="oa")

    # 首批两份模板登记。原件仍保存在仓库的“要素式模板”目录；normalized 副本由编译器生成。
    # 使用 driver-level SQL，避免 SQLAlchemy 将 JSON 中的 ``:true`` 误识别为绑定参数。
    op.get_bind().exec_driver_sql(
        """
        WITH template_row AS (
          INSERT INTO oa.legal_document_template
            (template_code, template_name, document_type, cause_code, cause_name,
             cause_aliases, party_role, procedure_stage, status)
          VALUES
            ('civil_complaint.private_lending', '要素式民间借贷纠纷起诉状', 'civil_complaint',
             'private_lending', '民间借贷纠纷', '[\"民间借贷\",\"借款合同\"]'::jsonb,
             'plaintiff', 'first_instance', 'active')
          ON CONFLICT (template_code) DO UPDATE SET updated_at = NOW()
          RETURNING id
        ), version_row AS (
          INSERT INTO oa.legal_document_template_version
            (template_id, version_no, source_path, sha256, file_size, source_format,
             schema_json, render_binding_json, compiler_report_json, parser_version, status)
          SELECT id, '1.0.0', '起诉状/要素式民间借贷纠纷起诉状.docx',
            'b28329f27ba054a57fe3c453a0ba4e29f28dff9405820104824688fe619750ac',
            36089, 'ooxml', '{\"schema_id\":\"private_lending_complaint.v1\"}'::jsonb,
            '{\"binding_id\":\"private_lending_complaint.v1\"}'::jsonb,
            '{\"seeded\":true,\"requires_legal_confirmation\":true}'::jsonb,
            'template-compiler-v1', 'active'
          FROM template_row
          ON CONFLICT (template_id, version_no) DO UPDATE SET updated_at = NOW()
          RETURNING id, template_id
        )
        UPDATE oa.legal_document_template t
        SET current_version_id = v.id, updated_at = NOW()
        FROM version_row v WHERE t.id = v.template_id;

        WITH template_row AS (
          INSERT INTO oa.legal_document_template
            (template_code, template_name, document_type, cause_code, cause_name,
             cause_aliases, party_role, procedure_stage, status)
          VALUES
            ('civil_defense.trademark_infringement', '要素式侵害商标权纠纷答辩状', 'civil_defense',
             'trademark_infringement', '侵害商标权纠纷', '[\"商标侵权\",\"侵害商标权\"]'::jsonb,
             'defendant', 'first_instance', 'draft')
          ON CONFLICT (template_code) DO UPDATE SET updated_at = NOW()
          RETURNING id
        )
        INSERT INTO oa.legal_document_template_version
          (template_id, version_no, source_path, sha256, file_size, source_format,
           schema_json, render_binding_json, compiler_report_json, parser_version, status)
        SELECT id, '1.0.0', '答辩状/要素式侵害商标权纠纷答辩状.docx',
          '59ece4063c53e35aaae188e24b45f8764dd33bdce943c30563d1a3fae49261aa',
          32547, 'ooxml', '{\"schema_id\":\"trademark_defense.v1\"}'::jsonb,
          '{\"binding_id\":\"trademark_defense.v1\"}'::jsonb,
          '{\"seeded\":true,\"requires_legal_confirmation\":true}'::jsonb,
          'template-compiler-v1', 'draft'
        FROM template_row
        ON CONFLICT (template_id, version_no) DO UPDATE SET updated_at = NOW();

        -- 首次插入模板时，同一 data-modifying CTE 的 UPDATE 看不到刚插入的目标行；
        -- 在两个 INSERT 完成后统一回填当前版本，兼容全新库与重复执行。
        UPDATE oa.legal_document_template AS t
        SET current_version_id = v.id, updated_at = NOW()
        FROM oa.legal_document_template_version AS v
        WHERE v.template_id = t.id
          AND v.version_no = '1.0.0'
          AND t.template_code IN (
            'civil_complaint.private_lending',
            'civil_defense.trademark_infringement'
          );
        """
    )


def downgrade() -> None:
    op.drop_constraint("fk_legal_generation_run_result_version", "legal_document_generation_run", schema="oa", type_="foreignkey")
    op.drop_table("legal_document_generation_event", schema="oa")
    op.drop_table("legal_document_user_input", schema="oa")
    op.drop_table("legal_document_review_issue", schema="oa")
    op.drop_table("legal_document_source", schema="oa")
    op.drop_table("legal_document_version", schema="oa")
    op.drop_table("legal_document_generation_run", schema="oa")
    op.drop_constraint("fk_legal_template_current_version", "legal_document_template", schema="oa", type_="foreignkey")
    op.drop_table("legal_document_template_version", schema="oa")
    op.drop_table("legal_document_template", schema="oa")
    op.execute("DROP SCHEMA IF EXISTS agent_runtime CASCADE")
    op.drop_index("idx_kb_document_legal_validity", table_name="kb_document", schema="oa")
    op.drop_column("kb_document", "cause_codes", schema="oa")
    op.drop_column("kb_document", "effective_to", schema="oa")
    op.drop_column("kb_document", "effective_from", schema="oa")
    op.drop_column("kb_document", "effective_status", schema="oa")
