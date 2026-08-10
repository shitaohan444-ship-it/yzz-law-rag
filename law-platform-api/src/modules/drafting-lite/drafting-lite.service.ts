import {
  BadRequestException,
  BadGatewayException,
  GatewayTimeoutException,
  HttpException,
  Injectable,
} from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import { Prisma } from '@prisma/client';
import { PrismaService } from '../../core/prisma/prisma.service';
import {
  DraftingLiteCause,
  DraftingLiteJob,
  DraftingLiteMaterialList,
  DraftingLiteMaterialSummary,
  PartyRecord,
} from './drafting-lite.types';

function normalizeUploadFilename(name: string): string {
  // busboy/multer interprets multipart filenames as latin-1. Browsers send UTF-8,
  // so Chinese names otherwise arrive as mojibake such as "è¦ç´ ...".
  const recovered = Buffer.from(name, 'latin1').toString('utf8');
  return recovered.includes('\uFFFD') ? name : recovered;
}

@Injectable()
export class DraftingLiteService {
  constructor(
    private readonly config: ConfigService,
    private readonly prisma: PrismaService,
  ) {}

  async listMaterials(input: {
    keyword: string;
    page: number;
    pageSize: number;
    caseStatus: string;
  }): Promise<DraftingLiteMaterialList> {
    const page = Number.isInteger(input.page) && input.page > 0 ? input.page : 1;
    const pageSize =
      Number.isInteger(input.pageSize) && input.pageSize > 0 && input.pageSize <= 100
        ? input.pageSize
        : 20;
    const categoryCode = {
      all: 'client_material',
      open: 'client_material_open',
      closed: 'client_material_closed',
    }[input.caseStatus];
    if (!categoryCode) {
      throw new BadRequestException({
        code: 'DRAFTING_LITE_CASE_STATUS_INVALID',
        message: '当事人材料状态筛选无效',
      });
    }
    const keyword = input.keyword.trim().slice(0, 100);
    const keywordFilter = keyword
      ? Prisma.sql`AND d.doc_title ILIKE ${`%${keyword}%`}`
      : Prisma.empty;
    const offset = (page - 1) * pageSize;
    type Row = {
      document_id: bigint;
      title: string;
      file_name: string;
      category_path: string[];
      embedding_status: string;
      last_uploaded_at: Date;
      source_count: bigint;
      image_total: number;
    };
    const baseCte = Prisma.sql`
      WITH RECURSIVE selected_categories AS (
        SELECT id FROM oa.kb_category
        WHERE category_code = ${categoryCode}
          AND deleted_at IS NULL AND status = 'active'
        UNION ALL
        SELECT child.id
        FROM oa.kb_category child
        JOIN selected_categories parent ON child.parent_id = parent.id
        WHERE child.deleted_at IS NULL AND child.status = 'active'
      ),
      category_paths AS (
        SELECT c.id, c.parent_id, ARRAY[c.category_name]::text[] AS path
        FROM oa.kb_category c
        WHERE c.parent_id IS NULL AND c.deleted_at IS NULL
        UNION ALL
        SELECT child.id, child.parent_id, parent.path || child.category_name
        FROM oa.kb_category child
        JOIN category_paths parent ON child.parent_id = parent.id
        WHERE child.deleted_at IS NULL
      )
    `;
    const [rows, counts] = await Promise.all([
      this.prisma.$queryRaw<Row[]>(Prisma.sql`
        ${baseCte}
        SELECT d.id AS document_id, d.doc_title AS title,
               COALESCE(a.original_file_name, a.file_name) AS file_name,
               cp.path AS category_path, d.embedding_status,
               COALESCE((
                 SELECT MAX(COALESCE(s.updated_at, s.created_at))
                 FROM oa.kb_document_source s
                 WHERE s.document_id = d.id AND s.deleted_at IS NULL
                   AND s.status = 'active'
               ), d.updated_at, d.created_at) AS last_uploaded_at,
               (
                 SELECT COUNT(*) FROM oa.kb_document_source s
                 WHERE s.document_id = d.id AND s.deleted_at IS NULL
                   AND s.status = 'active'
               )::bigint AS source_count,
               COALESCE(d.image_total, 0) AS image_total
        FROM oa.kb_document d
        JOIN oa.sys_attachment a ON a.id = d.attachment_id
        JOIN category_paths cp ON cp.id = d.category_id
        WHERE d.category_id IN (SELECT id FROM selected_categories)
          AND d.embedding_status = 'success'
          AND d.deleted_at IS NULL AND d.status = 'active'
          AND a.deleted_at IS NULL AND a.status = 'active'
          ${keywordFilter}
        ORDER BY last_uploaded_at DESC, d.id DESC
        LIMIT ${pageSize} OFFSET ${offset}
      `),
      this.prisma.$queryRaw<{ total: bigint }[]>(Prisma.sql`
        ${baseCte}
        SELECT COUNT(*)::bigint AS total
        FROM oa.kb_document d
        JOIN oa.sys_attachment a ON a.id = d.attachment_id
        WHERE d.category_id IN (SELECT id FROM selected_categories)
          AND d.embedding_status = 'success'
          AND d.deleted_at IS NULL AND d.status = 'active'
          AND a.deleted_at IS NULL AND a.status = 'active'
          ${keywordFilter}
      `),
    ]);
    return {
      items: rows.map(
        (row): DraftingLiteMaterialSummary => ({
          document_id: row.document_id.toString(),
          title: row.title,
          file_name: row.file_name,
          category_path: row.category_path,
          embedding_status: row.embedding_status,
          last_uploaded_at: row.last_uploaded_at.toISOString(),
          source_count: Number(row.source_count),
          image_total: Number(row.image_total),
        }),
      ),
      total: Number(counts[0]?.total ?? 0),
      page,
      page_size: pageSize,
    };
  }

  async create(
    files: Express.Multer.File[],
    cause: string,
    knowledgeDocumentIds: string[],
  ): Promise<DraftingLiteJob> {
    const normalizedIds = this.normalizeKnowledgeIds(knowledgeDocumentIds);
    await this.validateKnowledgeMaterials(normalizedIds);
    const form = new FormData();
    for (const file of files) {
      form.append(
        'files',
        new Blob([new Uint8Array(file.buffer)], {
          type: file.mimetype || 'application/octet-stream',
        }),
        normalizeUploadFilename(file.originalname),
      );
    }
    form.append('cause', cause || 'auto');
    form.append('knowledge_document_ids', JSON.stringify(normalizedIds));
    return this.requestJson<DraftingLiteJob>('/drafting-lite/jobs', {
      method: 'POST',
      body: form,
    });
  }

  private normalizeKnowledgeIds(values: string[]): string[] {
    const normalized = [...new Set(values.map((value) => value.trim()))];
    if (normalized.some((value) => !/^[1-9]\d*$/.test(value))) {
      throw new BadRequestException({
        code: 'DRAFTING_LITE_KNOWLEDGE_IDS_INVALID',
        message: '知识库材料ID无效',
      });
    }
    return normalized;
  }

  private async validateKnowledgeMaterials(ids: string[]): Promise<void> {
    if (!ids.length) return;
    const bigintIds = ids.map((value) => BigInt(value));
    const rows = await this.prisma.$queryRaw<{ id: bigint }[]>(Prisma.sql`
      WITH RECURSIVE client_categories AS (
        SELECT id FROM oa.kb_category
        WHERE category_code = 'client_material'
          AND deleted_at IS NULL AND status = 'active'
        UNION ALL
        SELECT child.id
        FROM oa.kb_category child
        JOIN client_categories parent ON child.parent_id = parent.id
        WHERE child.deleted_at IS NULL AND child.status = 'active'
      )
      SELECT d.id
      FROM oa.kb_document d
      WHERE d.id IN (${Prisma.join(bigintIds)})
        AND d.category_id IN (SELECT id FROM client_categories)
        AND d.embedding_status = 'success'
        AND d.deleted_at IS NULL AND d.status = 'active'
    `);
    const valid = new Set(rows.map((row) => row.id.toString()));
    if (ids.some((id) => !valid.has(id))) {
      throw new BadRequestException({
        code: 'DRAFTING_LITE_KNOWLEDGE_MATERIAL_NOT_READY',
        message: '所选知识库材料不存在、未完成入库或不属于当事人案件材料',
      });
    }
  }

  get(jobId: string): Promise<DraftingLiteJob> {
    return this.requestJson(`/drafting-lite/jobs/${encodeURIComponent(jobId)}`, {
      method: 'GET',
    });
  }

  cancel(jobId: string): Promise<DraftingLiteJob> {
    return this.requestJson(
      `/drafting-lite/jobs/${encodeURIComponent(jobId)}/cancel`,
      { method: 'POST' },
    );
  }

  listCauses(): Promise<{ items: DraftingLiteCause[] }> {
    return this.requestJson('/drafting-lite/causes', { method: 'GET' });
  }

  selectCause(jobId: string, cause: string): Promise<DraftingLiteJob> {
    return this.requestJson(
      `/drafting-lite/jobs/${encodeURIComponent(jobId)}/cause`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ cause }),
      },
    );
  }

  confirmParties(
    jobId: string,
    input: { version: number; parties: PartyRecord[]; confirmed: boolean },
  ): Promise<DraftingLiteJob> {
    return this.requestJson(
      `/drafting-lite/jobs/${encodeURIComponent(jobId)}/parties`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(input),
      },
    );
  }

  async download(jobId: string): Promise<{ body: Buffer; contentType: string; disposition: string }> {
    return this.downloadPath(
      `/drafting-lite/jobs/${encodeURIComponent(jobId)}/download`,
    );
  }

  async downloadArtifact(
    jobId: string,
    artifactType: 'complaint' | 'evidence_directory' | 'evidence_package',
  ): Promise<{ body: Buffer; contentType: string; disposition: string }> {
    return this.downloadPath(
      `/drafting-lite/jobs/${encodeURIComponent(jobId)}/artifacts/${encodeURIComponent(artifactType)}/download`,
    );
  }

  private async downloadPath(path: string): Promise<{ body: Buffer; contentType: string; disposition: string }> {
    const response = await this.request(
      path,
      { method: 'GET' },
    );
    return {
      body: Buffer.from(await response.arrayBuffer()),
      contentType:
        response.headers.get('content-type') ??
        'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
      disposition:
        response.headers.get('content-disposition') ??
        "attachment; filename*=UTF-8''draft.docx",
    };
  }

  private baseUrl(): string {
    return (
      this.config.get<string>('RAG_API_BASE_URL') ?? 'http://127.0.0.1:8000'
    ).replace(/\/$/, '');
  }

  private async requestJson<T>(path: string, init: RequestInit): Promise<T> {
    const response = await this.request(path, init);
    try {
      return (await response.json()) as T;
    } catch {
      throw new BadGatewayException({
        code: 'DRAFTING_LITE_INVALID_RESPONSE',
        message: '文书生成服务返回了无效响应',
      });
    }
  }

  private async request(path: string, init: RequestInit): Promise<Response> {
    const controller = new AbortController();
    const timeoutMs = Number(
      this.config.get<number>('DRAFTING_LITE_GATEWAY_TIMEOUT_MS') ?? 900000,
    );
    const timeout = setTimeout(() => controller.abort(), timeoutMs);
    const serviceToken = this.config.get<string>('RAG_SERVICE_TOKEN')?.trim();
    try {
      const response = await fetch(`${this.baseUrl()}${path}`, {
        ...init,
        headers: {
          ...(init.headers ?? {}),
          ...(serviceToken && { Authorization: `Bearer ${serviceToken}` }),
        },
        signal: controller.signal,
      });
      if (!response.ok) {
        let message = '文书生成服务拒绝了请求';
        try {
          const payload = (await response.json()) as { detail?: string };
          if (typeof payload.detail === 'string') message = payload.detail;
        } catch {
          // 保持脱敏的默认错误。
        }
        if (response.status >= 400 && response.status < 500) {
          throw new HttpException(
            { code: 'DRAFTING_LITE_REQUEST_REJECTED', message },
            response.status,
          );
        }
        throw new BadGatewayException({
          code: 'DRAFTING_LITE_UPSTREAM_ERROR',
          message: '文书生成服务处理失败，请稍后重试',
        });
      }
      return response;
    } catch (error: unknown) {
      if (error instanceof HttpException) throw error;
      if (controller.signal.aborted) {
        throw new GatewayTimeoutException({
          code: 'DRAFTING_LITE_TIMEOUT',
          message: '文书生成服务响应超时',
        });
      }
      throw new BadGatewayException({
        code: 'DRAFTING_LITE_UNAVAILABLE',
        message: '暂时无法连接文书生成服务',
      });
    } finally {
      clearTimeout(timeout);
    }
  }
}
