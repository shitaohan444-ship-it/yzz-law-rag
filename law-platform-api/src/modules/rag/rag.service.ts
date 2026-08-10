import {
  BadGatewayException,
  GatewayTimeoutException,
  HttpException,
  Injectable,
  Logger,
} from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import { randomUUID } from 'node:crypto';
import { ChatRagDto } from './dto/chat-rag.dto';
import { SearchRagDto } from './dto/search-rag.dto';
import {
  RagChatResponse,
  RagDocumentMarkdown,
  RagDocumentChunks,
  RagDocumentStatus,
  RagIngestResponse,
  RagSearchResponse,
  RagSourcePromotionResponse,
  RagVerifyRestoreResponse,
} from './rag.types';

type JsonRecord = Record<string, unknown>;
type RagHttpMethod = 'GET' | 'POST' | 'DELETE';
type DocumentRouteMode = 'legacy' | 'allowlist' | 'initial_mac' | 'mac';
type DocumentMutationKind = 'initial_ingest' | 'force_ingest' | 'advanced';

interface RequestTarget {
  baseUrl: string;
  serviceToken?: string;
  processor: 'query' | 'legacy' | 'mac';
}

@Injectable()
export class RagService {
  private readonly logger = new Logger(RagService.name);

  constructor(private readonly config: ConfigService) {}

  createDocumentRequestId(): string {
    return randomUUID();
  }

  async search(dto: SearchRagDto): Promise<RagSearchResponse> {
    const payload = await this.post('/search', {
      query: dto.query,
      ...(dto.top_k !== undefined && { top_k: dto.top_k }),
      ...(dto.doc_ids !== undefined && { doc_ids: dto.doc_ids }),
    });
    if (!this.isSearchResponse(payload)) {
      throw new BadGatewayException({
        code: 'RAG_INVALID_RESPONSE',
        message: '知识库返回了无法识别的检索结果',
      });
    }
    return payload;
  }

  async chat(dto: ChatRagDto): Promise<RagChatResponse> {
    const payload = await this.post('/chat', {
      question: dto.question,
      ...(dto.session_id !== undefined && { session_id: dto.session_id }),
      ...(dto.top_k !== undefined && { top_k: dto.top_k }),
      ...(dto.doc_ids !== undefined && { doc_ids: dto.doc_ids }),
      ...(dto.case_id !== undefined && { case_id: dto.case_id }),
    });
    if (!this.isChatResponse(payload)) {
      throw new BadGatewayException({
        code: 'RAG_INVALID_RESPONSE',
        message: '知识库返回了无法识别的问答结果',
      });
    }
    return payload;
  }

  async ingestDocument(
    docId: string,
    force = false,
    options?: {
      generateDescription?: boolean;
      analyzeImages?: boolean;
      routingDocId?: string;
      requestId?: string;
    },
  ): Promise<RagIngestResponse> {
    const timeoutMs = Number(
      this.config.get<number>('RAG_INGEST_TIMEOUT_MS') ?? 900000,
    );
    const payload = await this.requestDocumentMutation(
      options?.routingDocId ?? docId,
      `/documents/${encodeURIComponent(docId)}/ingest?force=${force}` +
        `${options?.generateDescription === undefined ? '' : `&generate_description=${options.generateDescription}`}` +
        `${options?.analyzeImages === undefined ? '' : `&analyze_images=${options.analyzeImages}`}`,
      'POST',
      undefined,
      timeoutMs,
      options?.requestId,
      force ? 'force_ingest' : 'initial_ingest',
    );
    if (
      !this.isRecord(payload) ||
      typeof payload.doc_id !== 'number' ||
      typeof payload.status !== 'string' ||
      typeof payload.chunk_count !== 'number'
    ) {
      throw new BadGatewayException({
        code: 'RAG_INVALID_RESPONSE',
        message: '知识库返回了无法识别的入库结果',
      });
    }
    return payload as unknown as RagIngestResponse;
  }

  async promoteDocument(
    stagingDocId: string,
    targetDocId: string,
    requestId?: string,
  ): Promise<RagIngestResponse> {
    const timeoutMs = Number(
      this.config.get<number>('RAG_INGEST_TIMEOUT_MS') ?? 900000,
    );
    const payload = await this.requestDocumentMutation(
      targetDocId,
      `/documents/${encodeURIComponent(stagingDocId)}/promote?target_doc_id=${encodeURIComponent(targetDocId)}`,
      'POST',
      undefined,
      timeoutMs,
      requestId,
    );
    if (
      !this.isRecord(payload) ||
      typeof payload.doc_id !== 'number' ||
      typeof payload.status !== 'string' ||
      typeof payload.chunk_count !== 'number'
    ) {
      throw new BadGatewayException({
        code: 'RAG_INVALID_RESPONSE',
        message: '知识库返回了无法识别的替换结果',
      });
    }
    return payload as unknown as RagIngestResponse;
  }

  async promoteSource(input: {
    stagingDocId: string;
    targetDocId: string;
    sourceId: string;
    mode: 'append' | 'replace';
    sourceTitle?: string;
    requestId?: string;
  }): Promise<RagSourcePromotionResponse> {
    const timeoutMs = Number(
      this.config.get<number>('RAG_INGEST_TIMEOUT_MS') ?? 900000,
    );
    const payload = await this.requestDocumentMutation(
      input.targetDocId,
      `/documents/${encodeURIComponent(input.stagingDocId)}/promote-source`,
      'POST',
      {
        target_doc_id: Number(input.targetDocId),
        source_id: Number(input.sourceId),
        mode: input.mode,
        ...(input.sourceTitle !== undefined && {
          source_title: input.sourceTitle,
        }),
      },
      timeoutMs,
      input.requestId,
    );
    if (
      !this.isRecord(payload) ||
      typeof payload.doc_id !== 'number' ||
      typeof payload.source_id !== 'number' ||
      typeof payload.status !== 'string' ||
      typeof payload.chunk_count !== 'number'
    ) {
      throw new BadGatewayException({
        code: 'RAG_INVALID_RESPONSE',
        message: '知识库返回了无法识别的源文件入库结果',
      });
    }
    return payload as unknown as RagSourcePromotionResponse;
  }

  async rebuildSources(
    targetDocId: string,
    items: Array<{ sourceId: string; stagingDocId: string }>,
    requestId?: string,
  ): Promise<RagIngestResponse> {
    const timeoutMs = Number(
      this.config.get<number>('RAG_INGEST_TIMEOUT_MS') ?? 900000,
    );
    const payload = await this.requestDocumentMutation(
      targetDocId,
      '/documents/rebuild-sources',
      'POST',
      {
        target_doc_id: Number(targetDocId),
        items: items.map((item) => ({
          source_id: Number(item.sourceId),
          staging_doc_id: Number(item.stagingDocId),
        })),
      },
      timeoutMs,
      requestId,
    );
    if (
      !this.isRecord(payload) ||
      typeof payload.doc_id !== 'number' ||
      typeof payload.status !== 'string' ||
      typeof payload.chunk_count !== 'number'
    ) {
      throw new BadGatewayException({
        code: 'RAG_INVALID_RESPONSE',
        message: '知识库返回了无法识别的多源重建结果',
      });
    }
    return payload as unknown as RagIngestResponse;
  }

  async cleanupStagingDocument(
    stagingDocId: string,
    routingDocId = stagingDocId,
    requestId?: string,
  ): Promise<void> {
    await this.requestDocumentMutation(
      routingDocId,
      `/documents/${encodeURIComponent(stagingDocId)}/staging`,
      'DELETE',
      undefined,
      undefined,
      requestId,
    );
  }

  async batchDeleteDocuments(docIds: string[]): Promise<string> {
    const requestId = this.createDocumentRequestId();
    for (const group of this.groupDocumentIds(docIds)) {
      await this.requestDocumentMutation(
        group[0],
        '/documents/batch-delete',
        'POST',
        { doc_ids: group.map((id) => Number(id)) },
        undefined,
        requestId,
      );
    }
    return requestId;
  }

  async verifyRestoreDocuments(
    docIds: string[],
  ): Promise<RagVerifyRestoreResponse> {
    const requestId = this.createDocumentRequestId();
    const items: RagVerifyRestoreResponse['items'] = [];
    for (const group of this.groupDocumentIds(docIds)) {
      const payload = await this.requestDocumentMutation(
        group[0],
        '/documents/verify-restore',
        'POST',
        { doc_ids: group.map((id) => Number(id)) },
        undefined,
        requestId,
      );
      if (
        !this.isRecord(payload) ||
        !Array.isArray(payload.items) ||
        !payload.items.every(
          (item) =>
            this.isRecord(item) &&
            typeof item.doc_id === 'number' &&
            typeof item.ok === 'boolean' &&
            typeof item.missing_chunks === 'number' &&
            Array.isArray(item.missing_images),
        )
      ) {
        throw new BadGatewayException({
          code: 'RAG_INVALID_RESPONSE',
          message: '知识库返回了无法识别的恢复校验结果',
          request_id: requestId,
        });
      }
      items.push(...(payload.items as RagVerifyRestoreResponse['items']));
    }
    return { items, request_id: requestId };
  }

  async getDocumentStatus(docId: string): Promise<RagDocumentStatus> {
    const payload = await this.requestDocumentRead(
      `/documents/${encodeURIComponent(docId)}`,
    );
    if (
      !this.isRecord(payload) ||
      typeof payload.doc_id !== 'number' ||
      typeof payload.embedding_status !== 'string' ||
      typeof payload.chunk_count !== 'number'
    ) {
      throw new BadGatewayException({
        code: 'RAG_INVALID_RESPONSE',
        message: '知识库返回了无法识别的文档状态',
      });
    }
    return payload as unknown as RagDocumentStatus;
  }

  async getDocumentMarkdown(
    docId: string,
    sourceId?: string,
  ): Promise<RagDocumentMarkdown> {
    const payload = await this.requestDocumentRead(
      `/documents/${encodeURIComponent(docId)}/markdown${sourceId ? `?source_id=${encodeURIComponent(sourceId)}` : ''}`,
    );
    if (
      !this.isRecord(payload) ||
      typeof payload.doc_id !== 'number' ||
      typeof payload.image_count !== 'number' ||
      typeof payload.markdown !== 'string'
    ) {
      throw new BadGatewayException({
        code: 'RAG_INVALID_RESPONSE',
        message: '知识库返回了无法识别的 Markdown',
      });
    }
    return payload as unknown as RagDocumentMarkdown;
  }

  async getDocumentChunks(
    docId: string,
    page: number,
    pageSize: number,
    sourceId?: string,
  ): Promise<RagDocumentChunks> {
    const payload = await this.requestDocumentRead(
      `/documents/${encodeURIComponent(docId)}/chunks?page=${page}&page_size=${pageSize}${sourceId ? `&source_id=${encodeURIComponent(sourceId)}` : ''}`,
    );
    if (
      !this.isRecord(payload) ||
      typeof payload.doc_id !== 'number' ||
      typeof payload.total !== 'number' ||
      typeof payload.page !== 'number' ||
      typeof payload.page_size !== 'number' ||
      !Array.isArray(payload.items) ||
      !payload.items.every((item) => this.isChunk(item))
    ) {
      throw new BadGatewayException({
        code: 'RAG_INVALID_RESPONSE',
        message: '知识库返回了无法识别的 Chunk 数据',
      });
    }
    return payload as unknown as RagDocumentChunks;
  }

  private async post(path: string, body: JsonRecord): Promise<unknown> {
    return this.request(path, 'POST', body);
  }

  private async request(
    path: string,
    method: RagHttpMethod,
    body?: JsonRecord,
    timeoutOverride?: number,
  ): Promise<unknown> {
    return this.requestTarget(
      {
        baseUrl: this.queryBaseUrl(),
        serviceToken: this.queryServiceToken(),
        processor: 'query',
      },
      path,
      method,
      body,
      timeoutOverride,
    );
  }

  private async requestDocumentMutation(
    routingDocId: string,
    path: string,
    method: RagHttpMethod,
    body?: JsonRecord,
    timeoutOverride?: number,
    requestId = this.createDocumentRequestId(),
    mutationKind: DocumentMutationKind = 'advanced',
  ): Promise<unknown> {
    const target = this.documentTarget(routingDocId, mutationKind);
    const payload = await this.requestTarget(
      target,
      path,
      method,
      body,
      timeoutOverride,
      requestId,
    );
    return this.isRecord(payload)
      ? { ...payload, request_id: requestId }
      : payload;
  }

  private async requestDocumentRead(
    path: string,
    requestId = this.createDocumentRequestId(),
  ): Promise<unknown> {
    const payload = await this.requestTarget(
      {
        baseUrl: this.queryBaseUrl(),
        serviceToken: this.queryServiceToken(),
        processor: 'legacy',
      },
      path,
      'GET',
      undefined,
      undefined,
      requestId,
    );
    return this.isRecord(payload)
      ? { ...payload, request_id: requestId }
      : payload;
  }

  private async requestTarget(
    target: RequestTarget,
    path: string,
    method: RagHttpMethod,
    body?: JsonRecord,
    timeoutOverride?: number,
    requestId?: string,
  ): Promise<unknown> {
    const timeoutMs =
      timeoutOverride ??
      Number(this.config.get<number>('RAG_API_TIMEOUT_MS') ?? 120000);
    const logContext = requestId
      ? ` request_id=${requestId} processor=${target.processor}`
      : '';
    if (requestId) {
      this.logger.log(
        `rag_document_request${logContext} method=${method} path=${path}`,
      );
    }

    // 知识库服务偶发连接重置（uvicorn 默认 keep-alive 5s 与本端连接池不匹配等），
    // 对同一目标的连接层错误自动重试。目标、Token 和 X-Request-ID 在重试间保持不变，
    // 严禁 Mac 失败后自动转发旧 RAG。
    const maxAttempts = 3;
    for (let attempt = 1; attempt <= maxAttempts; attempt += 1) {
      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), timeoutMs);
      try {
        const response = await fetch(`${target.baseUrl}${path}`, {
          method,
          headers: {
            ...(body !== undefined && { 'Content-Type': 'application/json' }),
            ...(target.serviceToken && {
              Authorization: `Bearer ${target.serviceToken}`,
            }),
            ...(requestId && { 'X-Request-ID': requestId }),
          },
          ...(body !== undefined && { body: JSON.stringify(body) }),
          signal: controller.signal,
        });

        let payload: unknown;
        try {
          payload = JSON.parse(await response.text()) as unknown;
        } catch {
          throw new BadGatewayException({
            code: 'RAG_INVALID_RESPONSE',
            message: '知识库返回了无效响应',
            ...(requestId && { request_id: requestId }),
          });
        }

        if (!response.ok) {
          this.throwUpstreamError(response.status, requestId);
        }
        if (requestId) {
          this.logger.log(`rag_document_response${logContext} status=success`);
        }
        return payload;
      } catch (error: unknown) {
        if (error instanceof HttpException) {
          if (requestId) {
            this.logger.warn(
              `rag_document_response${logContext} status=failed http_status=${error.getStatus()}`,
            );
          }
          throw error;
        }
        if (controller.signal.aborted) {
          throw new GatewayTimeoutException({
            code: 'RAG_TIMEOUT',
            message: '知识库处理超时，请稍后重试',
            ...(requestId && { request_id: requestId }),
          });
        }
        if (attempt < maxAttempts) {
          await new Promise((resolve) => setTimeout(resolve, attempt * 250));
          continue;
        }
        throw new BadGatewayException({
          code: 'RAG_UNAVAILABLE',
          message: '暂时无法连接知识库服务',
          ...(requestId && { request_id: requestId }),
        });
      } finally {
        clearTimeout(timeout);
      }
    }
    throw new BadGatewayException({
      code: 'RAG_UNAVAILABLE',
      message: '暂时无法连接知识库服务',
      ...(requestId && { request_id: requestId }),
    });
  }

  private throwUpstreamError(status: number, requestId?: string): never {
    if ((status >= 400 && status < 500) || status === 503) {
      const messages: Record<number, string> = {
        400: '知识库无法处理该请求',
        401: '知识库身份校验失败',
        403: '没有权限访问相关知识',
        404: '请求的知识范围不存在',
        409: '文档正在处理或当前状态不允许该操作',
        422: '知识库请求参数不符合要求',
        429: '请求过于频繁，请稍后重试',
        503: '文档处理服务暂不可用',
      };
      throw new HttpException(
        {
          code: 'RAG_REQUEST_REJECTED',
          message: messages[status] ?? '知识库拒绝了该请求',
          ...(requestId && { request_id: requestId }),
        },
        status,
      );
    }
    throw new BadGatewayException({
      code: 'RAG_UPSTREAM_ERROR',
      message: '知识库服务处理失败，请稍后重试',
      ...(requestId && { request_id: requestId }),
    });
  }

  private queryBaseUrl(): string {
    return (
      this.config.get<string>('RAG_API_BASE_URL') ?? 'http://127.0.0.1:8000'
    ).replace(/\/$/, '');
  }

  private documentBaseUrl(): string {
    const configured = this.config
      .get<string>('RAG_DOCUMENT_API_BASE_URL')
      ?.trim();
    return configured ? configured.replace(/\/$/, '') : this.queryBaseUrl();
  }

  private queryServiceToken(): string | undefined {
    return this.config.get<string>('RAG_SERVICE_TOKEN')?.trim() || undefined;
  }

  private documentServiceToken(): string | undefined {
    return (
      this.config.get<string>('RAG_DOCUMENT_SERVICE_TOKEN')?.trim() ||
      this.queryServiceToken()
    );
  }

  private documentTarget(
    docId: string,
    mutationKind: DocumentMutationKind,
  ): RequestTarget {
    const queryBaseUrl = this.queryBaseUrl();
    const documentBaseUrl = this.documentBaseUrl();
    const routeMode = this.documentRouteMode();
    const useMac =
      routeMode === 'mac' ||
      (routeMode === 'allowlist' && this.macAllowlist().has(docId)) ||
      (routeMode === 'initial_mac' && mutationKind === 'initial_ingest');
    if (!useMac || documentBaseUrl === queryBaseUrl) {
      return {
        baseUrl: queryBaseUrl,
        serviceToken: this.queryServiceToken(),
        processor: 'legacy',
      };
    }
    return {
      baseUrl: documentBaseUrl,
      serviceToken: this.documentServiceToken(),
      processor: 'mac',
    };
  }

  private documentRouteMode(): DocumentRouteMode {
    const configured = this.config
      .get<string>('RAG_DOCUMENT_ROUTE_MODE')
      ?.trim();
    return (configured || 'allowlist') as DocumentRouteMode;
  }

  private macAllowlist(): Set<string> {
    const raw =
      this.config.get<string>('RAG_DOCUMENT_MAC_ALLOWLIST')?.trim() ?? '';
    return new Set(
      raw
        .split(/[\s,]+/)
        .map((value) => value.trim())
        .filter((value) => /^[1-9]\d*$/.test(value)),
    );
  }

  private groupDocumentIds(docIds: string[]): string[][] {
    const legacy: string[] = [];
    const mac: string[] = [];
    for (const docId of docIds) {
      const target = this.documentTarget(docId, 'advanced');
      (target.processor === 'mac' ? mac : legacy).push(docId);
    }
    return [legacy, mac].filter((group) => group.length > 0);
  }

  private isSearchResponse(value: unknown): value is RagSearchResponse {
    return (
      this.isRecord(value) &&
      typeof value.query === 'string' &&
      typeof value.total === 'number' &&
      Array.isArray(value.hits) &&
      value.hits.every((hit) => this.isRagHit(hit))
    );
  }

  private isChatResponse(value: unknown): value is RagChatResponse {
    return (
      this.isRecord(value) &&
      typeof value.question === 'string' &&
      typeof value.answer === 'string' &&
      Array.isArray(value.refs) &&
      value.refs.every(
        (ref) =>
          this.isRagHit(ref) &&
          this.isRecord(ref) &&
          typeof ref.ref_id === 'number',
      ) &&
      typeof value.hits_count === 'number'
    );
  }

  private isRagHit(value: unknown): boolean {
    if (
      !this.isRecord(value) ||
      typeof value.chunk_id !== 'string' ||
      typeof value.doc_id !== 'number' ||
      !(typeof value.doc_title === 'string' || value.doc_title === null) ||
      typeof value.source !== 'string' ||
      typeof value.chunk_idx !== 'number' ||
      typeof value.text !== 'string' ||
      typeof value.score !== 'number'
    ) {
      return false;
    }
    return (
      value.official_link === undefined ||
      value.official_link === null ||
      this.isOfficialLink(value.official_link)
    );
  }

  private isOfficialLink(value: unknown): boolean {
    if (
      !this.isRecord(value) ||
      value.provider !== 'npc_flk' ||
      value.source_name !== '国家法律法规数据库' ||
      value.label !== '官网最新版' ||
      typeof value.url !== 'string'
    ) {
      return false;
    }
    try {
      const url = new URL(value.url);
      return (
        url.protocol === 'https:' &&
        url.hostname === 'flk.npc.gov.cn' &&
        url.port === '' &&
        url.username === '' &&
        url.password === '' &&
        url.pathname === '/detail' &&
        url.hash === '' &&
        [...url.searchParams.keys()].length === 1 &&
        /^[0-9a-f]{32}$/.test(url.searchParams.get('id') ?? '')
      );
    } catch {
      return false;
    }
  }

  private isChunk(value: unknown): boolean {
    return (
      this.isRecord(value) &&
      typeof value.chunk_id === 'string' &&
      typeof value.chunk_idx === 'number' &&
      typeof value.text === 'string' &&
      typeof value.char_count === 'number'
    );
  }

  private isRecord(value: unknown): value is JsonRecord {
    return typeof value === 'object' && value !== null && !Array.isArray(value);
  }
}
