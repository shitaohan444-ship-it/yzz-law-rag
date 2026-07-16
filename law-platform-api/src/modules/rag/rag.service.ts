import {
  BadGatewayException,
  GatewayTimeoutException,
  HttpException,
  Injectable,
} from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
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
} from './rag.types';

type JsonRecord = Record<string, unknown>;

@Injectable()
export class RagService {
  constructor(private readonly config: ConfigService) {}

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
    force: boolean,
  ): Promise<RagIngestResponse> {
    const timeoutMs = Number(
      this.config.get<number>('RAG_INGEST_TIMEOUT_MS') ?? 900000,
    );
    const payload = await this.request(
      `/documents/${encodeURIComponent(docId)}/ingest?force=${force}`,
      'POST',
      undefined,
      timeoutMs,
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
  ): Promise<RagIngestResponse> {
    const timeoutMs = Number(
      this.config.get<number>('RAG_INGEST_TIMEOUT_MS') ?? 900000,
    );
    const payload = await this.request(
      `/documents/${encodeURIComponent(stagingDocId)}/promote?target_doc_id=${encodeURIComponent(targetDocId)}`,
      'POST',
      undefined,
      timeoutMs,
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
  }): Promise<RagSourcePromotionResponse> {
    const timeoutMs = Number(
      this.config.get<number>('RAG_INGEST_TIMEOUT_MS') ?? 900000,
    );
    const payload = await this.request(
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
  ): Promise<RagIngestResponse> {
    const timeoutMs = Number(
      this.config.get<number>('RAG_INGEST_TIMEOUT_MS') ?? 900000,
    );
    const payload = await this.request(
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

  async cleanupStagingDocument(stagingDocId: string): Promise<void> {
    await this.request(
      `/documents/${encodeURIComponent(stagingDocId)}/staging`,
      'DELETE',
    );
  }

  async getDocumentStatus(docId: string): Promise<RagDocumentStatus> {
    const payload = await this.request(
      `/documents/${encodeURIComponent(docId)}`,
      'GET',
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
    const payload = await this.request(
      `/documents/${encodeURIComponent(docId)}/markdown${sourceId ? `?source_id=${encodeURIComponent(sourceId)}` : ''}`,
      'GET',
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
    const payload = await this.request(
      `/documents/${encodeURIComponent(docId)}/chunks?page=${page}&page_size=${pageSize}${sourceId ? `&source_id=${encodeURIComponent(sourceId)}` : ''}`,
      'GET',
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
    method: 'GET' | 'POST' | 'DELETE',
    body?: JsonRecord,
    timeoutOverride?: number,
  ): Promise<unknown> {
    const baseUrl = (
      this.config.get<string>('RAG_API_BASE_URL') ?? 'http://127.0.0.1:8000'
    ).replace(/\/$/, '');
    const timeoutMs =
      timeoutOverride ??
      Number(this.config.get<number>('RAG_API_TIMEOUT_MS') ?? 120000);
    const serviceToken = this.config.get<string>('RAG_SERVICE_TOKEN')?.trim();
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), timeoutMs);

    try {
      const response = await fetch(`${baseUrl}${path}`, {
        method,
        headers: {
          ...(body !== undefined && { 'Content-Type': 'application/json' }),
          ...(serviceToken && { Authorization: `Bearer ${serviceToken}` }),
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
        });
      }

      if (!response.ok) {
        this.throwUpstreamError(response.status);
      }
      return payload;
    } catch (error: unknown) {
      if (error instanceof HttpException) throw error;
      if (controller.signal.aborted) {
        throw new GatewayTimeoutException({
          code: 'RAG_TIMEOUT',
          message: '知识库处理超时，请稍后重试',
        });
      }
      throw new BadGatewayException({
        code: 'RAG_UNAVAILABLE',
        message: '暂时无法连接知识库服务',
      });
    } finally {
      clearTimeout(timeout);
    }
  }

  private throwUpstreamError(status: number): never {
    if (status >= 400 && status < 500) {
      const messages: Record<number, string> = {
        400: '知识库无法处理该请求',
        401: '知识库身份校验失败',
        403: '没有权限访问相关知识',
        404: '请求的知识范围不存在',
        422: '检索或问答参数不符合要求',
        429: '请求过于频繁，请稍后重试',
      };
      throw new HttpException(
        {
          code: 'RAG_REQUEST_REJECTED',
          message: messages[status] ?? '知识库拒绝了该请求',
        },
        status,
      );
    }
    throw new BadGatewayException({
      code: 'RAG_UPSTREAM_ERROR',
      message: '知识库服务处理失败，请稍后重试',
    });
  }

  private isSearchResponse(value: unknown): value is RagSearchResponse {
    return (
      this.isRecord(value) &&
      typeof value.query === 'string' &&
      typeof value.total === 'number' &&
      Array.isArray(value.hits)
    );
  }

  private isChatResponse(value: unknown): value is RagChatResponse {
    return (
      this.isRecord(value) &&
      typeof value.question === 'string' &&
      typeof value.answer === 'string' &&
      Array.isArray(value.refs) &&
      typeof value.hits_count === 'number'
    );
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
