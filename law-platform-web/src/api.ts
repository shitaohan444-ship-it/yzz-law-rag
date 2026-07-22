import type {
  ChatResponse,
  KnowledgeCategoryNode,
  KnowledgeCategoryTreeResponse,
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
  TrashListResponse,
  KnowledgeDocumentBatchRestoreResponse,
  KnowledgeDocumentBatchPurgeResponse,
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
  categoryId: string;
}): Promise<KnowledgeDocumentUploadResponse> {
  const body = new FormData();
  body.append('file', input.file);
  body.append('title', input.title.trim());
  body.append('category_id', input.categoryId);
  return requestJson('/api/rag/documents', { method: 'POST', body });
}

export function replaceKnowledgeDocument(input: {
  docId: string;
  file: File;
  title: string;
  categoryId: string;
}): Promise<KnowledgeDocumentReplaceResponse> {
  const body = new FormData();
  body.append('file', input.file);
  body.append('title', input.title.trim());
  body.append('category_id', input.categoryId);
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
  categoryId?: string;
  status?: string;
  keyword?: string;
}): Promise<KnowledgeDocumentListResponse> {
  const params = new URLSearchParams({
    page: String(filters.page),
    page_size: String(filters.pageSize ?? 5),
  });
  if (filters.categoryId) params.set('category_id', filters.categoryId);
  if (filters.status) params.set('status', filters.status);
  if (filters.keyword?.trim()) params.set('keyword', filters.keyword.trim());
  return requestJson(`/api/rag/documents?${params}`, { method: 'GET' });
}

export function listKnowledgeCategories(
  includeInactive = false,
): Promise<KnowledgeCategoryTreeResponse> {
  const suffix = includeInactive ? '?include_inactive=true' : '';
  return requestJson(`/api/rag/categories${suffix}`, { method: 'GET' });
}

export function createKnowledgeCategory(input: {
  name: string;
  aliases: string[];
  parentId: string | null;
  assignable: boolean;
  sensitive: boolean;
}): Promise<KnowledgeCategoryNode> {
  return requestJson('/api/rag/categories', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      name: input.name.trim(),
      aliases: input.aliases,
      parent_id: input.parentId,
      assignable: input.assignable,
      sensitive: input.sensitive,
    }),
  });
}

export function updateKnowledgeCategory(
  categoryId: string,
  input: Partial<{
    name: string;
    aliases: string[];
    parent_id: string | null;
    sort_order: number;
    assignable: boolean;
    sensitive: boolean;
    status: 'active' | 'inactive';
  }>,
): Promise<KnowledgeCategoryNode> {
  return requestJson(`/api/rag/categories/${encodeURIComponent(categoryId)}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(input),
  });
}

export function deactivateKnowledgeCategory(
  categoryId: string,
): Promise<KnowledgeCategoryNode> {
  return requestJson(`/api/rag/categories/${encodeURIComponent(categoryId)}`, {
    method: 'DELETE',
  });
}

export function updateKnowledgeDocumentCategory(input: {
  docId: string;
  categoryId: string;
}): Promise<import('./types').KnowledgeDocument> {
  return requestJson(
    `/api/rag/documents/${encodeURIComponent(input.docId)}/category`,
    {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ category_id: input.categoryId }),
    },
  );
}

export function updateKnowledgeDocumentTitle(input: {
  docId: string;
  title: string;
}): Promise<import('./types').KnowledgeDocument> {
  return requestJson(
    `/api/rag/documents/${encodeURIComponent(input.docId)}/title`,
    {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title: input.title.trim() }),
    },
  );
}

export function batchMoveKnowledgeDocuments(input: {
  docIds: string[];
  categoryId: string;
}): Promise<import('./types').KnowledgeDocumentBatchMoveResponse> {
  return requestJson('/api/rag/documents/batch-move', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      doc_ids: input.docIds,
      category_id: input.categoryId,
    }),
  });
}

export function batchDeleteKnowledgeDocuments(
  docIds: string[],
): Promise<import('./types').KnowledgeDocumentBatchDeleteResponse> {
  return requestJson('/api/rag/documents/batch-delete', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ doc_ids: docIds }),
  });
}

export function listTrashDocuments(filters: {
  page: number;
  pageSize?: number;
  categoryId?: string;
  keyword?: string;
  sort?: 'deleted_at' | 'title';
  order?: 'asc' | 'desc';
}): Promise<TrashListResponse> {
  const params = new URLSearchParams({
    page: String(filters.page),
    page_size: String(filters.pageSize ?? 20),
    sort: filters.sort ?? 'deleted_at',
    order: filters.order ?? 'desc',
  });
  if (filters.categoryId) params.set('category_id', filters.categoryId);
  if (filters.keyword?.trim()) params.set('keyword', filters.keyword.trim());
  return requestJson(`/api/rag/documents/trash?${params}`, { method: 'GET' });
}

export function batchRestoreKnowledgeDocuments(input: {
  docIds: string[];
  categoryOverrides?: Record<string, string>;
}): Promise<KnowledgeDocumentBatchRestoreResponse> {
  return postJson('/api/rag/documents/batch-restore', {
    doc_ids: input.docIds,
    ...(input.categoryOverrides && Object.keys(input.categoryOverrides).length > 0
      ? { category_overrides: input.categoryOverrides }
      : {}),
  });
}

export function batchPurgeKnowledgeDocuments(
  docIds: string[],
): Promise<KnowledgeDocumentBatchPurgeResponse> {
  return postJson('/api/rag/documents/batch-purge', { doc_ids: docIds });
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
