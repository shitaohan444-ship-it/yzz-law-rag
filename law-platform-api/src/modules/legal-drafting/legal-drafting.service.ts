import {
  BadRequestException,
  ConflictException,
  Injectable,
  NotFoundException,
  UnauthorizedException,
} from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import { createHash, createHmac, randomUUID, timingSafeEqual } from 'node:crypto';
import { Prisma } from '@prisma/client';
import { PrismaService } from '../../core/prisma/prisma.service';
import { AttachmentService } from '../attachments/attachment.service';
import {
  ActorDto,
  ConfirmTemplateDto,
  CreateGenerationDto,
  ReviewVersionDto,
  SubmitUserInputsDto,
} from './dto/create-generation.dto';
import { ClaimRunDto, HeartbeatDto, WorkerEventDto } from './dto/worker.dto';
import {
  GenerationRunStatus,
  RunTokenPayload,
  TERMINAL_RUN_STATUSES,
} from './legal-drafting.types';

type DbRecord = Record<string, unknown>;

export interface RunRow extends DbRecord {
  id: bigint;
  thread_id: string;
  case_id: bigint;
  template_version_id: bigint | null;
  selected_material_ids: unknown;
  selected_evidence_ids: unknown;
  allowed_doc_ids: unknown;
  run_status: GenerationRunStatus;
  input_version: number;
  event_seq: bigint;
  lease_owner: string | null;
}

export interface TemplateMatch extends DbRecord {
  template_id: bigint;
  template_version_id: bigint;
  template_code: string;
  template_name: string;
  document_type: string;
  cause_code: string | null;
  party_role: string | null;
  version_no: string;
}

@Injectable()
export class LegalDraftingService {
  constructor(
    private readonly prisma: PrismaService,
    private readonly config: ConfigService,
    private readonly attachments: AttachmentService,
  ) {}

  async matchTemplates(input: {
    documentType?: string;
    causeCode?: string;
    partyRole?: string;
  }) {
    const rows = await this.prisma.$queryRaw<TemplateMatch[]>(Prisma.sql`
      SELECT t.id AS template_id, v.id AS template_version_id,
             t.template_code, t.template_name, t.document_type,
             t.cause_code, t.party_role, v.version_no
      FROM oa.legal_document_template t
      JOIN oa.legal_document_template_version v ON v.id = t.current_version_id
      WHERE t.deleted_at IS NULL AND t.status = 'active'
        AND v.deleted_at IS NULL AND v.status = 'active'
        ${input.documentType ? Prisma.sql`AND t.document_type = ${input.documentType}` : Prisma.empty}
        ${input.causeCode ? Prisma.sql`AND (t.cause_code = ${input.causeCode} OR t.cause_aliases ? ${input.causeCode})` : Prisma.empty}
        ${input.partyRole ? Prisma.sql`AND (t.party_role = ${input.partyRole} OR t.party_role IS NULL)` : Prisma.empty}
      ORDER BY
        CASE WHEN t.cause_code = ${input.causeCode ?? ''} THEN 0 ELSE 1 END,
        CASE WHEN t.party_role = ${input.partyRole ?? ''} THEN 0 ELSE 1 END,
        t.template_name
      LIMIT 10
    `);
    return {
      items: rows.map((row, index) => ({
        ...row,
        confidence: index === 0 && row.cause_code === input.causeCode ? 1 : 0.75,
        requires_confirmation: index > 0 || row.cause_code !== input.causeCode,
      })),
    };
  }

  async createGeneration(dto: CreateGenerationDto) {
    if (dto.fixed_identity !== true) {
      throw new BadRequestException('内部试运行仅允许固定开发身份');
    }
    const caseId = this.positiveBigInt(dto.case_id, 'case_id');
    const actorId = this.positiveBigInt(dto.actor_id, 'actor_id');
    this.assertFixedActor(actorId);
    const materialIds = this.bigIntList(dto.material_ids, 'material_ids');
    const evidenceIds = this.bigIntList(dto.evidence_ids, 'evidence_ids');
    const docIds = this.bigIntList(
      dto.knowledge_document_ids,
      'knowledge_document_ids',
    );

    if (dto.idempotency_key) {
      const existing = await this.prisma.$queryRaw<RunRow[]>(Prisma.sql`
        SELECT * FROM oa.legal_document_generation_run
        WHERE idempotency_key = ${dto.idempotency_key} AND deleted_at IS NULL
        LIMIT 1
      `);
      if (existing[0]) return existing[0];
    }

    const caseRow = await this.prisma.case_main.findFirst({
      where: { id: caseId, deleted_at: null, status: 'active' },
      select: { id: true },
    });
    if (!caseRow) throw new NotFoundException('案件不存在或不可用');

    await this.assertCaseScopedIds(caseId, materialIds, evidenceIds);
    await this.assertKnowledgeDocuments(docIds);

    let templateVersionId = dto.template_version_id
      ? this.positiveBigInt(dto.template_version_id, 'template_version_id')
      : null;
    let runStatus: GenerationRunStatus = 'pending';
    if (templateVersionId) {
      await this.assertTemplateVersion(templateVersionId);
    } else {
      const matches = await this.matchTemplates({
        documentType: dto.document_type,
        causeCode: dto.cause_code,
        partyRole: dto.party_role,
      });
      if (matches.items.length === 1 && !matches.items[0].requires_confirmation) {
        templateVersionId = matches.items[0].template_version_id;
      } else {
        runStatus = 'waiting_template_confirmation';
      }
    }

    const permissionSnapshot = {
      case_id: caseId.toString(),
      material_ids: materialIds.map(String),
      evidence_ids: evidenceIds.map(String),
      knowledge_document_ids: docIds.map(String),
      actor_id: actorId.toString(),
      fixed_identity: dto.fixed_identity,
      captured_at: new Date().toISOString(),
    };
    const snapshotHash = createHash('sha256')
      .update(JSON.stringify(permissionSnapshot))
      .digest('hex');
    const threadId = randomUUID();
    const rows = await this.prisma.$queryRaw<RunRow[]>(Prisma.sql`
      INSERT INTO oa.legal_document_generation_run
        (thread_id, idempotency_key, case_id, template_version_id,
         document_type, cause_code, party_role, run_status, current_node, progress,
         selected_material_ids, selected_evidence_ids, allowed_doc_ids,
         permission_snapshot_json, snapshot_hash, model_config_json,
         prompt_version, parser_version, created_by, updated_by)
      VALUES
        (${threadId}::uuid, ${dto.idempotency_key ?? null}, ${caseId}, ${templateVersionId},
         ${dto.document_type}, ${dto.cause_code ?? null}, ${dto.party_role ?? null},
         ${runStatus}, ${runStatus === 'waiting_template_confirmation' ? 'match_template' : 'queued'}, 0,
         ${JSON.stringify(materialIds.map(String))}::jsonb,
         ${JSON.stringify(evidenceIds.map(String))}::jsonb,
         ${JSON.stringify(docIds.map(String))}::jsonb,
         ${JSON.stringify(permissionSnapshot)}::jsonb,
         ${snapshotHash},
         ${JSON.stringify({
           provider: 'bailian',
           text_model: 'qwen3.7-plus',
           vision_model: 'qwen3-vl-plus',
           retrieval_config_version: 'legal-research-v1',
         })}::jsonb,
         'legal-drafting-v2', 'template-compiler-v1',
         ${actorId}, ${actorId})
      RETURNING *
    `);
    return rows[0];
  }

  async getGeneration(id: bigint) {
    const runs = await this.prisma.$queryRaw<DbRecord[]>(Prisma.sql`
      SELECT r.*, t.template_name, tv.version_no AS template_version_no,
             dv.docx_attachment_id, dv.pdf_attachment_id,
             dv.version_status AS result_version_status,
             dv.structured_content_json, dv.provenance_json,
             dv.audit_report_json
      FROM oa.legal_document_generation_run r
      LEFT JOIN oa.legal_document_template_version tv ON tv.id = r.template_version_id
      LEFT JOIN oa.legal_document_template t ON t.id = tv.template_id
      LEFT JOIN oa.legal_document_version dv ON dv.id = r.result_version_id
      WHERE r.id = ${id} AND r.deleted_at IS NULL
    `);
    if (!runs[0]) throw new NotFoundException('生成任务不存在');
    const [issues, inputs, events, sources] = await Promise.all([
      this.prisma.$queryRaw<DbRecord[]>(Prisma.sql`
        SELECT * FROM oa.legal_document_review_issue
        WHERE run_id = ${id} ORDER BY id
      `),
      this.prisma.$queryRaw<DbRecord[]>(Prisma.sql`
        SELECT * FROM oa.legal_document_user_input
        WHERE run_id = ${id} ORDER BY input_version, id
      `),
      this.prisma.$queryRaw<DbRecord[]>(Prisma.sql`
        SELECT event_seq, event_type, payload_json, created_at
        FROM oa.legal_document_generation_event
        WHERE run_id = ${id} ORDER BY event_seq DESC LIMIT 50
      `),
      this.prisma.$queryRaw<DbRecord[]>(Prisma.sql`
        SELECT s.* FROM oa.legal_document_source s
        JOIN oa.legal_document_generation_run r ON r.result_version_id = s.version_id
        WHERE r.id = ${id} ORDER BY s.field_id, s.id
      `),
    ]);
    return {
      ...runs[0],
      issues,
      sources,
      user_inputs: inputs,
      events: events.reverse(),
    };
  }

  async confirmTemplate(id: bigint, dto: ConfirmTemplateDto) {
    const versionId = this.positiveBigInt(
      dto.template_version_id,
      'template_version_id',
    );
    const actorId = this.positiveBigInt(dto.actor_id, 'actor_id');
    this.assertFixedActor(actorId);
    await this.assertTemplateVersion(versionId);
    const rows = await this.prisma.$queryRaw<RunRow[]>(Prisma.sql`
      UPDATE oa.legal_document_generation_run
      SET template_version_id = ${versionId}, run_status = 'pending',
          current_node = 'queued', updated_by = ${actorId}, updated_at = NOW()
      WHERE id = ${id} AND deleted_at IS NULL
        AND run_status IN ('pending', 'waiting_template_confirmation')
      RETURNING *
    `);
    if (!rows[0]) throw new ConflictException('当前任务状态不允许更换模板');
    return rows[0];
  }

  async submitInputs(id: bigint, dto: SubmitUserInputsDto) {
    // 兼容已加载旧前端产生的 "01"，并统一处理 PostgreSQL bigint 的字符串序列化。
    const inputVersion = Number(dto.input_version);
    if (!Number.isInteger(inputVersion) || inputVersion < 1) {
      throw new BadRequestException('input_version 必须为正整数');
    }
    const actorId = this.positiveBigInt(dto.actor_id, 'actor_id');
    this.assertFixedActor(actorId);
    return this.prisma.$transaction(async (tx) => {
      const runs = await tx.$queryRaw<RunRow[]>(Prisma.sql`
        SELECT * FROM oa.legal_document_generation_run
        WHERE id = ${id} AND deleted_at IS NULL FOR UPDATE
      `);
      const run = runs[0];
      if (!run) throw new NotFoundException('生成任务不存在');
      if (run.run_status !== 'waiting_user_input') {
        throw new ConflictException('任务当前不在等待人工输入状态');
      }
      const expectedInputVersion = Number(run.input_version) + 1;
      if (inputVersion !== expectedInputVersion) {
        throw new ConflictException(
          `input_version 已变化，当前应为 ${expectedInputVersion}`,
        );
      }
      for (const item of dto.inputs) {
        await tx.$executeRaw(Prisma.sql`
          INSERT INTO oa.legal_document_user_input
            (run_id, input_version, field_id, value_json, resolution_type,
             source_note, submitted_by)
          VALUES (${id}, ${inputVersion}, ${item.field_id},
                  ${JSON.stringify(item.value ?? null)}::jsonb,
                  ${item.resolution_type}, ${item.source_note ?? null}, ${actorId})
        `);
      }
      const updated = await tx.$queryRaw<RunRow[]>(Prisma.sql`
        UPDATE oa.legal_document_generation_run
        SET input_version = ${inputVersion}, run_status = 'pending',
            current_node = 'resume', waiting_reason = NULL,
            updated_by = ${actorId}, updated_at = NOW()
        WHERE id = ${id} RETURNING *
      `);
      return updated[0];
    });
  }

  async resume(id: bigint, dto: ActorDto) {
    const actorId = this.positiveBigInt(dto.actor_id, 'actor_id');
    this.assertFixedActor(actorId);
    const rows = await this.prisma.$queryRaw<RunRow[]>(Prisma.sql`
      UPDATE oa.legal_document_generation_run
      SET run_status = 'pending', current_node = 'resume', waiting_reason = NULL,
          lease_owner = NULL, lease_expires_at = NULL,
          error_code = NULL, error_message = NULL, completed_at = NULL,
          updated_by = ${actorId}, updated_at = NOW()
      WHERE id = ${id} AND deleted_at IS NULL
        AND run_status IN ('waiting_user_input', 'waiting_template_confirmation', 'failed')
      RETURNING *
    `);
    if (!rows[0]) throw new ConflictException('当前任务状态不允许恢复');
    return rows[0];
  }

  async cancel(id: bigint, dto: ActorDto) {
    const actorId = this.positiveBigInt(dto.actor_id, 'actor_id');
    this.assertFixedActor(actorId);
    const rows = await this.prisma.$queryRaw<RunRow[]>(Prisma.sql`
      UPDATE oa.legal_document_generation_run
      SET run_status = 'cancelled', cancelled_at = NOW(), current_node = 'cancelled',
          lease_expires_at = NOW(), updated_by = ${actorId}, updated_at = NOW()
      WHERE id = ${id} AND deleted_at IS NULL
        AND run_status NOT IN ('approved', 'cancelled')
      RETURNING *
    `);
    if (!rows[0]) throw new ConflictException('当前任务不能取消');
    return rows[0];
  }

  async claimRun(dto: ClaimRunDto) {
    const leaseSeconds = dto.lease_seconds ?? Number(
      this.config.get('LEGAL_DRAFTING_LEASE_SECONDS') ?? 120,
    );
    const rows = await this.prisma.$queryRaw<RunRow[]>(Prisma.sql`
      UPDATE oa.legal_document_generation_run r
      SET run_status = 'claimed', lease_owner = ${dto.worker_id},
          lease_expires_at = NOW() + (${leaseSeconds} * INTERVAL '1 second'),
          heartbeat_at = NOW(), started_at = COALESCE(started_at, NOW()),
          current_node = COALESCE(current_node, 'claimed'), updated_at = NOW()
      WHERE r.id = (
        SELECT id FROM oa.legal_document_generation_run
        WHERE deleted_at IS NULL AND template_version_id IS NOT NULL
          AND (
            run_status = 'pending'
            OR (run_status IN ('claimed', 'running') AND lease_expires_at < NOW())
          )
        ORDER BY created_at
        FOR UPDATE SKIP LOCKED LIMIT 1
      )
      RETURNING r.*
    `);
    const run = rows[0];
    if (!run) return { run: null };
    return {
      run,
      run_token: this.signRunToken(run),
      lease_seconds: leaseSeconds,
    };
  }

  async heartbeat(id: bigint, dto: HeartbeatDto) {
    const leaseSeconds = dto.lease_seconds ?? Number(
      this.config.get('LEGAL_DRAFTING_LEASE_SECONDS') ?? 120,
    );
    const updated = await this.prisma.$queryRaw<RunRow[]>(Prisma.sql`
      UPDATE oa.legal_document_generation_run
      SET heartbeat_at = NOW(),
          lease_expires_at = NOW() + (${leaseSeconds} * INTERVAL '1 second'),
          updated_at = NOW()
      WHERE id = ${id} AND lease_owner = ${dto.worker_id}
        AND run_status IN ('claimed', 'running', 'reviewing', 'rewriting', 'rendering')
      RETURNING *
    `);
    if (updated[0]) return { ok: true, cancel_requested: false };
    const rows = await this.prisma.$queryRaw<RunRow[]>(Prisma.sql`
      SELECT * FROM oa.legal_document_generation_run
      WHERE id = ${id} AND lease_owner = ${dto.worker_id} AND deleted_at IS NULL
    `);
    if (rows[0]?.run_status === 'cancelled') {
      return { ok: true, cancel_requested: true };
    }
    throw new ConflictException('Worker 未持有任务租约或任务状态不允许刷新');
  }

  async getCaseSnapshot(id: bigint, runToken: string) {
    const token = this.verifyRunToken(runToken);
    if (token.runId !== id.toString()) throw new UnauthorizedException('run token 与任务不匹配');
    const runRows = await this.prisma.$queryRaw<RunRow[]>(Prisma.sql`
      SELECT * FROM oa.legal_document_generation_run WHERE id = ${id} AND deleted_at IS NULL
    `);
    const run = runRows[0];
    if (!run || run.case_id.toString() !== token.caseId) {
      throw new UnauthorizedException('run token 已失效');
    }
    const materialIds = this.jsonIdList(run.selected_material_ids);
    const evidenceIds = this.jsonIdList(run.selected_evidence_ids);
    const [caseRows, parties, materials, evidence, userInputs, templateRows] = await Promise.all([
      this.prisma.$queryRaw<DbRecord[]>(Prisma.sql`
        SELECT * FROM oa.case_main WHERE id = ${run.case_id} AND deleted_at IS NULL
      `),
      this.prisma.$queryRaw<DbRecord[]>(Prisma.sql`
        SELECT cp.*, to_jsonb(pm) AS party
        FROM oa.case_party cp LEFT JOIN oa.party_main pm ON pm.id = cp.party_id
        WHERE cp.case_id = ${run.case_id} AND cp.deleted_at IS NULL ORDER BY cp.id
      `),
      materialIds.length
        ? this.prisma.$queryRaw<DbRecord[]>(Prisma.sql`
            SELECT m.*, to_jsonb(a) - 'storage_path' - 'object_key' AS attachment
            FROM oa.case_material m
            LEFT JOIN oa.sys_attachment a ON a.id = m.attachment_id
            WHERE m.case_id = ${run.case_id} AND m.id IN (${Prisma.join(materialIds)})
              AND m.deleted_at IS NULL ORDER BY m.id
          `)
        : Promise.resolve([]),
      evidenceIds.length
        ? this.prisma.$queryRaw<DbRecord[]>(Prisma.sql`
            SELECT * FROM oa.evidence_item
            WHERE case_id = ${run.case_id} AND id IN (${Prisma.join(evidenceIds)})
              AND deleted_at IS NULL ORDER BY sort_order, id
          `)
        : Promise.resolve([]),
      this.prisma.$queryRaw<DbRecord[]>(Prisma.sql`
        SELECT field_id, value_json, resolution_type, source_note, input_version
        FROM oa.legal_document_user_input WHERE run_id = ${id}
        ORDER BY input_version, id
      `),
      this.prisma.$queryRaw<DbRecord[]>(Prisma.sql`
        SELECT v.*, t.template_code, t.template_name, t.document_type,
               t.cause_code, t.party_role
        FROM oa.legal_document_template_version v
        JOIN oa.legal_document_template t ON t.id = v.template_id
        WHERE v.id = ${run.template_version_id}
      `),
    ]);
    if (!caseRows[0]) throw new NotFoundException('案件快照不可用');
    const snapshot = {
      run: {
        id: run.id,
        thread_id: run.thread_id,
        case_id: run.case_id,
        cause_code: run.cause_code,
        input_version: run.input_version,
        allowed_knowledge_document_ids: this.jsonIdList(run.allowed_doc_ids).map(String),
      },
      case: caseRows[0],
      parties,
      materials,
      evidence,
      user_inputs: userInputs,
      template: templateRows[0],
    };
    const snapshotHash = createHash('sha256')
      .update(
        JSON.stringify(snapshot, (_key, value) =>
          typeof value === 'bigint' ? value.toString() : value,
        ),
      )
      .digest('hex');
    await this.prisma.$executeRaw(Prisma.sql`
      UPDATE oa.legal_document_generation_run
      SET snapshot_hash = ${snapshotHash}, updated_at = NOW()
      WHERE id = ${id}
    `);
    return snapshot;
  }

  async authorizeMaterial(
    runId: bigint,
    materialId: bigint,
    runToken: string,
  ): Promise<bigint> {
    const token = this.verifyRunToken(runToken);
    if (
      token.runId !== runId.toString() ||
      !token.materialIds.includes(materialId.toString())
    ) {
      throw new UnauthorizedException('材料不在当前任务授权快照中');
    }
    const rows = await this.prisma.$queryRaw<{ attachment_id: bigint | null }[]>(
      Prisma.sql`
        SELECT attachment_id FROM oa.case_material
        WHERE id = ${materialId} AND case_id = ${BigInt(token.caseId)}
          AND deleted_at IS NULL
      `,
    );
    if (!rows[0]?.attachment_id) {
      throw new NotFoundException('材料附件不存在');
    }
    return rows[0].attachment_id;
  }

  async persistArtifacts(
    runId: bigint,
    runToken: string,
    files: {
      docx?: Express.Multer.File[];
      pdf?: Express.Multer.File[];
    },
    metadataText: string,
  ) {
    const token = this.verifyRunToken(runToken);
    if (token.runId !== runId.toString()) {
      throw new UnauthorizedException('run token 与任务不匹配');
    }
    const docx = files.docx?.[0];
    if (!docx) throw new BadRequestException('缺少 DOCX 产物');
    if (!metadataText || metadataText.length > 5_000_000) {
      throw new BadRequestException('metadata 缺失或超过大小限制');
    }
    let metadata: Record<string, unknown>;
    try {
      metadata = JSON.parse(metadataText) as Record<string, unknown>;
    } catch {
      throw new BadRequestException('metadata 必须是 JSON 对象');
    }
    if (!metadata || Array.isArray(metadata) || typeof metadata !== 'object') {
      throw new BadRequestException('metadata 必须是 JSON 对象');
    }

    const runRows = await this.prisma.$queryRaw<
      (RunRow & { created_by: bigint; document_type: string })[]
    >(Prisma.sql`
      SELECT * FROM oa.legal_document_generation_run
      WHERE id = ${runId} AND case_id = ${BigInt(token.caseId)}
        AND deleted_at IS NULL
    `);
    const run = runRows[0];
    if (!run) throw new NotFoundException('生成任务不存在');
    if (run.run_status === 'cancelled') {
      throw new ConflictException('已取消任务不能保存产物');
    }

    const uploaded: bigint[] = [];
    try {
      const docxAttachmentId = await this.attachments.upload({
        fileData: docx.buffer,
        filename: docx.originalname || `legal-draft-${runId}.docx`,
        bizType: 'legal_document_generation',
        bizId: runId,
        // MinIO 对象键只接受受控英文分类；AI 草稿属性由业务状态和 remark 表达。
        category: 'pleading',
        uploadedBy: run.created_by,
        contentType:
          docx.mimetype ||
          'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        prefix: 'legal-documents',
        entityNo: `run-${runId}`,
      });
      uploaded.push(docxAttachmentId);
      let pdfAttachmentId: bigint | null = null;
      const pdf = files.pdf?.[0];
      if (pdf) {
        pdfAttachmentId = await this.attachments.upload({
          fileData: pdf.buffer,
          filename: pdf.originalname || `legal-draft-${runId}.pdf`,
          bizType: 'legal_document_generation',
          bizId: runId,
          category: 'pleading',
          uploadedBy: run.created_by,
          contentType: pdf.mimetype || 'application/pdf',
          prefix: 'legal-documents',
          entityNo: `run-${runId}`,
        });
        uploaded.push(pdfAttachmentId);
      }

      return await this.prisma.$transaction(async (tx) => {
        const now = new Date();
        const document = await tx.legal_document.create({
          data: {
            case_id: run.case_id,
            document_title: String(
              metadata.title || `要素式法律文书（AI草稿-${runId}）`,
            ).slice(0, 255),
            document_type: run.document_type,
            version_no: '1',
            draft_employee_id: run.created_by,
            document_status: 'ai_draft',
            attachment_id: docxAttachmentId,
            created_by: run.created_by,
            updated_by: run.created_by,
            created_at: now,
            updated_at: now,
            status: 'active',
            remark: 'AI 草稿，须经律师审核；内部试运行产物',
          },
        });
        const versionRows = await tx.$queryRaw<{ id: bigint }[]>(Prisma.sql`
          INSERT INTO oa.legal_document_version
            (legal_document_id, generation_run_id, version_no, version_kind,
             version_status, structured_content_json, provenance_json,
             audit_report_json, docx_attachment_id, pdf_attachment_id, created_by)
          VALUES
            (${document.id}, ${runId}, 1, 'ai_generated', 'pending_review',
             ${JSON.stringify(metadata.structured_document ?? {})}::jsonb,
             ${JSON.stringify(metadata.provenance ?? {})}::jsonb,
             ${JSON.stringify(metadata.audit_report ?? {})}::jsonb,
             ${docxAttachmentId}, ${pdfAttachmentId}, ${run.created_by})
          RETURNING id
        `);
        const versionId = versionRows[0].id;

        const provenance = metadata.provenance;
        if (provenance && !Array.isArray(provenance) && typeof provenance === 'object') {
          for (const [fieldId, refs] of Object.entries(
            provenance as Record<string, unknown>,
          )) {
            if (!Array.isArray(refs)) continue;
            for (const ref of refs.slice(0, 50)) {
              if (!ref || Array.isArray(ref) || typeof ref !== 'object') continue;
              const source = ref as Record<string, unknown>;
              await tx.$executeRaw(Prisma.sql`
                INSERT INTO oa.legal_document_source
                  (version_id, field_id, source_type, material_id, evidence_id,
                   knowledge_document_id, chunk_id, attachment_id, page_no,
                   quote_text, content_hash)
                VALUES
                  (${versionId}, ${fieldId.slice(0, 160)},
                   ${String(source.source_type || 'unknown').slice(0, 40)},
                   ${this.nullableBigInt(source.material_id)},
                   ${this.nullableBigInt(source.evidence_id)},
                   ${this.nullableBigInt(source.knowledge_document_id ?? source.doc_id)},
                   ${source.chunk_id ? String(source.chunk_id).slice(0, 160) : null},
                   ${this.nullableBigInt(source.attachment_id)},
                   ${this.nullableInteger(source.page_no)},
                   ${source.quote_text ? String(source.quote_text).slice(0, 4000) : null},
                   ${source.content_hash ? String(source.content_hash).slice(0, 64) : null})
              `);
            }
          }
        }

        const reviewIssues = metadata.review_issues;
        if (Array.isArray(reviewIssues)) {
          for (const raw of reviewIssues.slice(0, 200)) {
            if (!raw || Array.isArray(raw) || typeof raw !== 'object') continue;
            const issue = raw as Record<string, unknown>;
            await tx.$executeRaw(Prisma.sql`
              INSERT INTO oa.legal_document_review_issue
                (run_id, version_id, issue_code, review_type, severity,
                 section_id, field_id, source_refs, message,
                 recommended_action, rewrite_target, review_round)
              VALUES
                (${runId}, ${versionId},
                 ${String(issue.issue_code || 'UNCLASSIFIED').slice(0, 80)},
                 ${String(issue.review_type || 'expression').slice(0, 40)},
                 ${String(issue.severity || 'minor').slice(0, 20)},
                 ${issue.section_id ? String(issue.section_id).slice(0, 120) : null},
                 ${issue.field_id ? String(issue.field_id).slice(0, 160) : null},
                 ${JSON.stringify(issue.source_refs ?? [])}::jsonb,
                 ${String(issue.message || '未提供说明').slice(0, 4000)},
                 ${issue.recommended_action ? String(issue.recommended_action).slice(0, 120) : null},
                 ${issue.rewrite_target ? String(issue.rewrite_target).slice(0, 160) : null},
                 ${this.nullableInteger(issue.review_round) ?? 1})
            `);
          }
        }

        await tx.$executeRaw(Prisma.sql`
          UPDATE oa.legal_document_generation_run
          SET result_document_id = ${document.id}, result_version_id = ${versionId},
              run_status = 'pending_lawyer_review', current_node = 'persist_result',
              progress = 100, completed_at = NOW(), updated_at = NOW()
          WHERE id = ${runId}
        `);
        return {
          ok: true,
          document_id: document.id,
          version_id: versionId,
          docx_attachment_id: docxAttachmentId,
          pdf_attachment_id: pdfAttachmentId,
        };
      });
    } catch (error) {
      await Promise.all(
        uploaded.map((attachmentId) =>
          this.attachments.delete(attachmentId, true).catch(() => undefined),
        ),
      );
      throw error;
    }
  }

  async recordEvent(id: bigint, dto: WorkerEventDto) {
    return this.prisma.$transaction(async (tx) => {
      const inserted = await tx.$queryRaw<{ id: bigint }[]>(Prisma.sql`
        INSERT INTO oa.legal_document_generation_event
          (run_id, event_seq, event_type, payload_json)
        VALUES (${id}, ${dto.event_seq}, ${dto.event_type},
                ${JSON.stringify(dto.payload ?? {})}::jsonb)
        ON CONFLICT (run_id, event_seq) DO NOTHING
        RETURNING id
      `);
      if (!inserted[0]) return { ok: true, duplicate: true };
      const status = dto.status;
      const completed = status && TERMINAL_RUN_STATUSES.has(status);
      const rows = await tx.$queryRaw<RunRow[]>(Prisma.sql`
        UPDATE oa.legal_document_generation_run
        SET event_seq = ${dto.event_seq},
            run_status = COALESCE(${status ?? null}, run_status),
            current_node = COALESCE(${dto.current_node ?? null}, current_node),
            progress = GREATEST(progress, COALESCE(${dto.progress ?? null}, progress)),
            waiting_reason = CASE
              WHEN ${status ?? null} IN ('waiting_user_input', 'waiting_template_confirmation')
                THEN ${JSON.stringify(dto.payload ?? {})}::jsonb
              ELSE waiting_reason END,
            error_code = COALESCE(${dto.error_code ?? null}, error_code),
            error_message = COALESCE(${dto.error_message ?? null}, error_message),
            completed_at = CASE WHEN ${completed ?? false} THEN NOW() ELSE completed_at END,
            updated_at = NOW()
        WHERE id = ${id} AND event_seq < ${dto.event_seq}
        RETURNING *
      `);
      if (!rows[0]) throw new ConflictException('事件序号小于当前任务序号');
      return { ok: true, duplicate: false, run: rows[0] };
    });
  }

  async listVersions(documentId: bigint) {
    const rows = await this.prisma.$queryRaw<DbRecord[]>(Prisma.sql`
      SELECT * FROM oa.legal_document_version
      WHERE legal_document_id = ${documentId} ORDER BY version_no DESC
    `);
    return { items: rows };
  }

  async reviewVersion(
    documentId: bigint,
    versionId: bigint,
    dto: ReviewVersionDto,
  ) {
    const actorId = this.positiveBigInt(dto.actor_id, 'actor_id');
    this.assertFixedActor(actorId);
    return this.prisma.$transaction(async (tx) => {
      const versions = await tx.$queryRaw<DbRecord[]>(Prisma.sql`
        SELECT * FROM oa.legal_document_version
        WHERE id = ${versionId} AND legal_document_id = ${documentId} FOR UPDATE
      `);
      if (!versions[0]) throw new NotFoundException('文书版本不存在');
      if (dto.action === 'approved') {
        if (versions[0].version_status === 'approved') {
          throw new ConflictException('该版本已经通过审核');
        }
        const approvedRows = await tx.$queryRaw<{ id: bigint; version_no: number }[]>(Prisma.sql`
          INSERT INTO oa.legal_document_version
            (legal_document_id, generation_run_id, version_no, version_kind,
             version_status, structured_content_json, provenance_json,
             audit_report_json, docx_attachment_id, pdf_attachment_id,
             approved_by, approved_at, created_by)
          SELECT source.legal_document_id, source.generation_run_id,
                 next_version.version_no, 'lawyer_approved', 'approved',
                 source.structured_content_json, source.provenance_json,
                 source.audit_report_json || jsonb_build_object(
                   'lawyer_review', jsonb_build_object(
                     'action', 'approved', 'comment', ${dto.comment ?? null},
                     'actor_id', ${actorId}::text, 'reviewed_at', NOW()
                   )
                 ),
                 source.docx_attachment_id, source.pdf_attachment_id,
                 ${actorId}, NOW(), ${actorId}
          FROM oa.legal_document_version source
          CROSS JOIN LATERAL (
            SELECT COALESCE(MAX(v.version_no), 0) + 1 AS version_no
            FROM oa.legal_document_version v
            WHERE v.legal_document_id = source.legal_document_id
          ) next_version
          WHERE source.id = ${versionId}
          RETURNING id, version_no
        `);
        const approved = approvedRows[0];
        await tx.$executeRaw(Prisma.sql`
          INSERT INTO oa.legal_document_source
            (version_id, field_id, section_id, source_type, material_id,
             evidence_id, knowledge_document_id, chunk_id, attachment_id,
             page_no, paragraph_no, table_index, cell_ref, quote_text, content_hash)
          SELECT ${approved.id}, field_id, section_id, source_type, material_id,
                 evidence_id, knowledge_document_id, chunk_id, attachment_id,
                 page_no, paragraph_no, table_index, cell_ref, quote_text, content_hash
          FROM oa.legal_document_source WHERE version_id = ${versionId}
        `);
        await tx.$executeRaw(Prisma.sql`
          UPDATE oa.legal_document_version
          SET version_status = 'superseded' WHERE id = ${versionId}
        `);
        await tx.$executeRaw(Prisma.sql`
          UPDATE oa.legal_document_generation_run
          SET result_version_id = ${approved.id}, run_status = 'approved',
              current_node = 'lawyer_approved', completed_at = NOW(),
              updated_by = ${actorId}, updated_at = NOW()
          WHERE result_version_id = ${versionId}
        `);
        await tx.$executeRaw(Prisma.sql`
          UPDATE oa.legal_document
          SET document_status = 'approved', version_no = ${approved.version_no.toString()},
              review_employee_id = ${actorId}, updated_by = ${actorId}, updated_at = NOW(),
              remark = COALESCE(${dto.comment ?? null}, remark)
          WHERE id = ${documentId}
        `);
        return {
          ok: true,
          status: 'approved',
          approved_version_id: approved.id,
          version_no: approved.version_no,
        };
      }

      await tx.$executeRaw(Prisma.sql`
        UPDATE oa.legal_document_version
        SET version_status = 'returned',
            audit_report_json = audit_report_json || jsonb_build_object(
              'lawyer_review', jsonb_build_object(
                'action', 'returned', 'comment', ${dto.comment ?? null},
                'actor_id', ${actorId}::text, 'reviewed_at', NOW()
              )
            )
        WHERE id = ${versionId}
      `);
      await tx.$executeRaw(Prisma.sql`
        UPDATE oa.legal_document_generation_run
        SET run_status = 'returned', current_node = 'lawyer_returned',
            waiting_reason = ${JSON.stringify({
              type: 'lawyer_returned',
              comment: dto.comment ?? '',
            })}::jsonb,
            completed_at = NOW(), updated_by = ${actorId}, updated_at = NOW()
        WHERE result_version_id = ${versionId}
      `);
      await tx.$executeRaw(Prisma.sql`
        UPDATE oa.legal_document
        SET document_status = 'draft', review_employee_id = ${actorId},
            updated_by = ${actorId}, updated_at = NOW(),
            remark = COALESCE(${dto.comment ?? null}, remark)
        WHERE id = ${documentId}
      `);
      return { ok: true, status: 'returned' };
    });
  }

  assertWorkerToken(value: string | undefined): void {
    const expected = String(
      this.config.get('LEGAL_DRAFTING_WORKER_TOKEN') ??
        this.config.get('RAG_SERVICE_TOKEN') ??
        '',
    );
    if (!expected || !value) throw new UnauthorizedException('缺少 Worker 服务凭证');
    const actualBuffer = Buffer.from(value);
    const expectedBuffer = Buffer.from(expected);
    if (
      actualBuffer.length !== expectedBuffer.length ||
      !timingSafeEqual(actualBuffer, expectedBuffer)
    ) {
      throw new UnauthorizedException('Worker 服务凭证无效');
    }
  }

  private async assertCaseScopedIds(
    caseId: bigint,
    materialIds: bigint[],
    evidenceIds: bigint[],
  ) {
    if (materialIds.length) {
      const count = await this.prisma.case_material.count({
        where: { id: { in: materialIds }, case_id: caseId, deleted_at: null },
      });
      if (count !== materialIds.length) {
        throw new BadRequestException('存在不属于当前案件或已删除的材料');
      }
    }
    if (evidenceIds.length) {
      const count = await this.prisma.evidence_item.count({
        where: { id: { in: evidenceIds }, case_id: caseId, deleted_at: null },
      });
      if (count !== evidenceIds.length) {
        throw new BadRequestException('存在不属于当前案件或已删除的证据');
      }
    }
  }

  private async assertKnowledgeDocuments(docIds: bigint[]) {
    if (!docIds.length) return;
    const count = await this.prisma.kb_document.count({
      where: { id: { in: docIds }, deleted_at: null, status: 'active' },
    });
    if (count !== docIds.length) {
      throw new BadRequestException('存在不可用的知识库文档');
    }
  }

  private async assertTemplateVersion(id: bigint) {
    const rows = await this.prisma.$queryRaw<{ id: bigint }[]>(Prisma.sql`
      SELECT v.id FROM oa.legal_document_template_version v
      JOIN oa.legal_document_template t ON t.id = v.template_id
      WHERE v.id = ${id} AND v.deleted_at IS NULL AND v.status = 'active'
        AND t.deleted_at IS NULL AND t.status = 'active'
    `);
    if (!rows[0]) throw new BadRequestException('模板版本不存在或未激活');
  }

  private positiveBigInt(value: string, field: string): bigint {
    try {
      const result = BigInt(value);
      if (result <= 0n) throw new Error('non-positive');
      return result;
    } catch {
      throw new BadRequestException(`${field} 必须为正整数`);
    }
  }

  private assertFixedActor(actorId: bigint): void {
    const configured = this.positiveBigInt(
      String(this.config.get('LEGAL_DRAFTING_DEV_ACTOR_ID') ?? '1'),
      'LEGAL_DRAFTING_DEV_ACTOR_ID',
    );
    if (actorId !== configured) {
      throw new UnauthorizedException('内部试运行仅允许固定开发律师身份');
    }
  }

  private bigIntList(values: string[], field: string): bigint[] {
    const unique = [...new Set(values)];
    return unique.map((value) => this.positiveBigInt(value, field));
  }

  private jsonIdList(value: unknown): bigint[] {
    if (!Array.isArray(value)) return [];
    return value.map((item) => BigInt(String(item)));
  }

  private runTokenSecret(): string {
    const secret = String(
      this.config.get('LEGAL_DRAFTING_RUN_TOKEN_SECRET') ??
        this.config.get('RAG_SERVICE_TOKEN') ??
        '',
    );
    if (secret.length < 32) {
      throw new UnauthorizedException('run token 密钥未配置或长度不足');
    }
    return secret;
  }

  private signRunToken(run: RunRow): string {
    const ttlSeconds = Number(
      this.config.get('LEGAL_DRAFTING_RUN_TOKEN_TTL_SECONDS') ?? 7200,
    );
    const payload: RunTokenPayload = {
      runId: run.id.toString(),
      caseId: run.case_id.toString(),
      materialIds: this.jsonIdList(run.selected_material_ids).map(String),
      evidenceIds: this.jsonIdList(run.selected_evidence_ids).map(String),
      knowledgeDocumentIds: this.jsonIdList(run.allowed_doc_ids).map(String),
      expiresAt: new Date(Date.now() + ttlSeconds * 1000).toISOString(),
    };
    const body = Buffer.from(JSON.stringify(payload)).toString('base64url');
    const signature = createHmac('sha256', this.runTokenSecret())
      .update(body)
      .digest('base64url');
    return `${body}.${signature}`;
  }

  private nullableBigInt(value: unknown): bigint | null {
    if (value === null || value === undefined || value === '') return null;
    try {
      const parsed = BigInt(String(value));
      return parsed > 0n ? parsed : null;
    } catch {
      return null;
    }
  }

  private nullableInteger(value: unknown): number | null {
    if (value === null || value === undefined || value === '') return null;
    const parsed = Number(value);
    return Number.isInteger(parsed) ? parsed : null;
  }

  private verifyRunToken(value: string): RunTokenPayload {
    const [body, signature] = value.split('.');
    if (!body || !signature) throw new UnauthorizedException('run token 格式错误');
    const expected = createHmac('sha256', this.runTokenSecret())
      .update(body)
      .digest('base64url');
    const actualBuffer = Buffer.from(signature);
    const expectedBuffer = Buffer.from(expected);
    if (
      actualBuffer.length !== expectedBuffer.length ||
      !timingSafeEqual(actualBuffer, expectedBuffer)
    ) {
      throw new UnauthorizedException('run token 签名无效');
    }
    const payload = JSON.parse(Buffer.from(body, 'base64url').toString()) as RunTokenPayload;
    if (new Date(payload.expiresAt).getTime() <= Date.now()) {
      throw new UnauthorizedException('run token 已过期');
    }
    return payload;
  }
}
