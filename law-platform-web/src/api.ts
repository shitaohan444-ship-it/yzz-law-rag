import type {
  ChatResponse,
  KnowledgeCategory,
  KnowledgeDocumentListResponse,
  KnowledgeDocumentMarkdown,
  KnowledgeDocumentChunks,
  KnowledgeDocumentStatus,
  KnowledgeDocumentSourcesResponse,
  KnowledgeDocumentSourceMutationResponse,
  KnowledgeDocumentUploadResponse,
  KnowledgeDocumentReplaceResponse,
  KnowledgeIngestResponse,
  SearchResponse,
} from './types';

const CLIENT_TIMEOUT_MS = 125_000;

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status?: number,
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

interface GatewayError {
  message?: string | string[];
}

async function postJson<T>(path: string, body: unknown): Promise<T> {
  return requestJson<T>(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
}

async function requestJson<T>(
  path: string,
  init: RequestInit,
  timeoutMs = CLIENT_TIMEOUT_MS,
): Promise<T> {
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), timeoutMs);

  try {
    const response = await fetch(path, { ...init, signal: controller.signal });
    const payload = (await response.json().catch(() => null)) as
      | GatewayError
      | T
      | null;
    if (!response.ok) {
      const message =
        payload &&
        typeof payload === 'object' &&
        'message' in payload &&
        (typeof payload.message === 'string' || Array.isArray(payload.message))
          ? Array.isArray(payload.message)
            ? payload.message.join('；')
            : payload.message
          : response.status === 504
            ? '知识库处理超时，请稍后重试'
            : '请求失败，请稍后重试';
      throw new ApiError(message, response.status);
    }
    if (payload === null) {
      throw new ApiError('平台网关返回了无效响应', response.status);
    }
    return payload as T;
  } catch (error: unknown) {
    if (error instanceof ApiError) throw error;
    if (error instanceof DOMException && error.name === 'AbortError') {
      throw new ApiError('请求等待时间过长，请稍后重试', 504);
    }
    throw new ApiError('无法连接平台网关，请确认后端已启动');
  } finally {
    window.clearTimeout(timeout);
  }
}

export function searchRag(query: string, topK: number): Promise<SearchResponse> {
  return postJson<SearchResponse>('/api/rag/search', {
    query: query.trim(),
    top_k: topK,
  });
}

export function chatRag(
  question: string,
  topK: number,
  sessionId: string,
): Promise<ChatResponse> {
  return postJson<ChatResponse>('/api/rag/chat', {
    question: question.trim(),
    top_k: topK,
    session_id: sessionId,
  });
}

export function uploadKnowledgeDocument(input: {
  file: File;
  title: string;
  category: KnowledgeCategory;
}): Promise<KnowledgeDocumentUploadResponse> {
  const body = new FormData();
  body.append('file', input.file);
  body.append('title', input.title.trim());
  body.append('category', input.category);
  return requestJson('/api/rag/documents', { method: 'POST', body });
}

export function replaceKnowledgeDocument(input: {
  docId: string;
  file: File;
  title: string;
  category: KnowledgeCategory;
}): Promise<KnowledgeDocumentReplaceResponse> {
  const body = new FormData();
  body.append('file', input.file);
  body.append('title', input.title.trim());
  body.append('category', input.category);
  return requestJson(
    `/api/rag/documents/${encodeURIComponent(input.docId)}/file`,
    { method: 'PUT', body },
    910_000,
  );
}

export function listKnowledgeDocumentSources(
  docId: string,
): Promise<KnowledgeDocumentSourcesResponse> {
  return requestJson(
    `/api/rag/documents/${encodeURIComponent(docId)}/sources`,
    { method: 'GET' },
  );
}

export function appendKnowledgeDocumentSource(input: {
  docId: string;
  file: File;
  sourceTitle: string;
}): Promise<KnowledgeDocumentSourceMutationResponse> {
  const body = new FormData();
  body.append('file', input.file);
  body.append('source_title', input.sourceTitle.trim());
  return requestJson(
    `/api/rag/documents/${encodeURIComponent(input.docId)}/sources`,
    { method: 'POST', body },
    910_000,
  );
}

export function replaceKnowledgeDocumentSource(input: {
  docId: string;
  sourceId: string;
  file: File;
  sourceTitle: string;
}): Promise<KnowledgeDocumentSourceMutationResponse> {
  const body = new FormData();
  body.append('file', input.file);
  body.append('source_title', input.sourceTitle.trim());
  return requestJson(
    `/api/rag/documents/${encodeURIComponent(input.docId)}/sources/${encodeURIComponent(input.sourceId)}/file`,
    { method: 'PUT', body },
    910_000,
  );
}

export function listKnowledgeDocuments(filters: {
  page: number;
  pageSize?: number;
  category?: string;
  status?: string;
  keyword?: string;
}): Promise<KnowledgeDocumentListResponse> {
  const params = new URLSearchParams({
    page: String(filters.page),
    page_size: String(filters.pageSize ?? 5),
  });
  if (filters.category) params.set('category', filters.category);
  if (filters.status) params.set('status', filters.status);
  if (filters.keyword?.trim()) params.set('keyword', filters.keyword.trim());
  return requestJson(`/api/rag/documents?${params}`, { method: 'GET' });
}

export function ingestKnowledgeDocument(
  docId: string,
  force = false,
): Promise<KnowledgeIngestResponse> {
  return requestJson(
    `/api/rag/documents/${encodeURIComponent(docId)}/ingest?force=${force}`,
    { method: 'POST' },
    910_000,
  );
}

export function getKnowledgeDocumentStatus(
  docId: string,
): Promise<KnowledgeDocumentStatus> {
  return requestJson(`/api/rag/documents/${encodeURIComponent(docId)}/status`, {
    method: 'GET',
  });
}

export function getKnowledgeDocumentMarkdown(
  docId: string,
  sourceId?: string,
): Promise<KnowledgeDocumentMarkdown> {
  const suffix = sourceId ? `?source_id=${encodeURIComponent(sourceId)}` : '';
  return requestJson(
    `/api/rag/documents/${encodeURIComponent(docId)}/markdown${suffix}`,
    { method: 'GET' },
  );
}

export function getKnowledgeDocumentChunks(
  docId: string,
  page = 1,
  pageSize = 20,
  sourceId?: string,
): Promise<KnowledgeDocumentChunks> {
  const params = new URLSearchParams({
    page: String(page),
    page_size: String(pageSize),
  });
  if (sourceId) params.set('source_id', sourceId);
  return requestJson(
    `/api/rag/documents/${encodeURIComponent(docId)}/chunks?${params}`,
    { method: 'GET' },
  );
}
