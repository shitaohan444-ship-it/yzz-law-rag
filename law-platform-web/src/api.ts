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

export async function requestJson<T>(
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

export function matchLegalDocumentTemplates(input: {
  documentType: string;
  causeCode: string;
  partyRole: string;
}): Promise<import('./types').LegalTemplateMatchResponse> {
  const params = new URLSearchParams({
    document_type: input.documentType,
    cause_code: input.causeCode,
    party_role: input.partyRole,
  });
  return requestJson(`/api/legal-document-templates/matches?${params}`, {
    method: 'GET',
  });
}

export function createLegalDraftingRun(input: {
  case_id: string;
  actor_id: string;
  material_ids: string[];
  evidence_ids: string[];
  knowledge_document_ids: string[];
}): Promise<import('./types').LegalDraftingRun> {
  return postJson('/api/legal-document-generations', {
    ...input,
    document_type: 'civil_complaint',
    cause_code: 'private_lending',
    party_role: 'plaintiff',
    fixed_identity: true,
    idempotency_key: crypto.randomUUID(),
  });
}

export function getLegalDraftingRun(
  runId: string,
): Promise<import('./types').LegalDraftingRun> {
  return requestJson(`/api/legal-document-generations/${encodeURIComponent(runId)}`, {
    method: 'GET',
  });
}

export function confirmLegalDraftingTemplate(input: {
  runId: string;
  templateVersionId: string;
  actorId: string;
}): Promise<import('./types').LegalDraftingRun> {
  return postJson(
    `/api/legal-document-generations/${encodeURIComponent(input.runId)}/template-confirmation`,
    { template_version_id: input.templateVersionId, actor_id: input.actorId },
  );
}

export function getLegalDocumentVersions(
  documentId: string,
): Promise<import('./types').LegalDocumentVersionResponse> {
  return requestJson(
    `/api/legal-documents/${encodeURIComponent(documentId)}/versions`,
    { method: 'GET' },
  );
}

export function submitLegalDraftingInputs(input: {
  runId: string;
  actorId: string;
  inputVersion: number;
  values: Record<string, string>;
}): Promise<import('./types').LegalDraftingRun> {
  return postJson(
    `/api/legal-document-generations/${encodeURIComponent(input.runId)}/inputs`,
    {
      actor_id: input.actorId,
      input_version: input.inputVersion,
      inputs: Object.entries(input.values).map(([field_id, value]) => ({
        field_id,
        value,
        resolution_type: 'confirmed',
        source_note: '律师在人工补充页面确认',
      })),
    },
  );
}

export function cancelLegalDraftingRun(
  runId: string,
  actorId: string,
): Promise<import('./types').LegalDraftingRun> {
  return postJson(
    `/api/legal-document-generations/${encodeURIComponent(runId)}/cancel`,
    { actor_id: actorId },
  );
}

export function resumeLegalDraftingRun(
  runId: string,
  actorId: string,
): Promise<import('./types').LegalDraftingRun> {
  return postJson(
    `/api/legal-document-generations/${encodeURIComponent(runId)}/resume`,
    { actor_id: actorId },
  );
}

export function reviewLegalDocumentVersion(input: {
  documentId: string;
  versionId: string;
  actorId: string;
  action: 'approved' | 'returned';
  comment?: string;
}): Promise<{ ok: boolean; status: string }> {
  return postJson(
    `/api/legal-documents/${encodeURIComponent(input.documentId)}/versions/${encodeURIComponent(input.versionId)}/review`,
    {
      actor_id: input.actorId,
      action: input.action,
      comment: input.comment,
    },
  );
}

export function createDraftingLiteJob(
  files: File[],
  cause: string,
  knowledgeDocumentIds: string[] = [],
): Promise<import('./types').DraftingLiteJob> {
  const body = new FormData();
  files.forEach((file) => body.append('files', file));
  body.append('cause', cause);
  body.append('knowledge_document_ids', JSON.stringify(knowledgeDocumentIds));
  return requestJson('/api/drafting-lite/jobs', {
    method: 'POST',
    body,
  }, 900_000);
}

export function listDraftingLiteCauses(): Promise<{
  items: import('./types').DraftingLiteCause[];
}> {
  return requestJson('/api/drafting-lite/causes', { method: 'GET' });
}

export function listDraftingLiteMaterials(input: {
  keyword?: string;
  page?: number;
  pageSize?: number;
  caseStatus?: 'all' | 'open' | 'closed';
} = {}): Promise<import('./types').DraftingLiteMaterialList> {
  const params = new URLSearchParams({
    keyword: input.keyword ?? '',
    page: String(input.page ?? 1),
    page_size: String(input.pageSize ?? 10),
    case_status: input.caseStatus ?? 'all',
  });
  return requestJson(`/api/drafting-lite/materials?${params}`, {
    method: 'GET',
  });
}

export function getDraftingLiteJob(
  jobId: string,
): Promise<import('./types').DraftingLiteJob> {
  return requestJson(`/api/drafting-lite/jobs/${encodeURIComponent(jobId)}`, {
    method: 'GET',
  });
}

export function cancelDraftingLiteJob(
  jobId: string,
): Promise<import('./types').DraftingLiteJob> {
  return postJson(
    `/api/drafting-lite/jobs/${encodeURIComponent(jobId)}/cancel`,
    {},
  );
}

export function selectDraftingLiteCause(
  jobId: string,
  cause: string,
): Promise<import('./types').DraftingLiteJob> {
  return postJson(
    `/api/drafting-lite/jobs/${encodeURIComponent(jobId)}/cause`,
    { cause },
  );
}

export function confirmDraftingLiteParties(input: {
  jobId: string;
  version: number;
  parties: import('./types').PartyRecord[];
}): Promise<import('./types').DraftingLiteJob> {
  return postJson(
    `/api/drafting-lite/jobs/${encodeURIComponent(input.jobId)}/parties`,
    {
      version: input.version,
      parties: input.parties,
      confirmed: true,
    },
  );
}

export async function downloadDraftingLiteDocument(
  jobId: string,
): Promise<{ blob: Blob; filename: string }> {
  return downloadDraftingLiteArtifact(jobId, 'complaint', true);
}

export async function downloadDraftingLiteArtifact(
  jobId: string,
  artifactType: 'complaint' | 'evidence_directory' | 'evidence_package',
  legacyComplaintRoute = false,
): Promise<{ blob: Blob; filename: string }> {
  const endpoint = legacyComplaintRoute && artifactType === 'complaint'
    ? `/api/drafting-lite/jobs/${encodeURIComponent(jobId)}/download`
    : `/api/drafting-lite/jobs/${encodeURIComponent(jobId)}/artifacts/${encodeURIComponent(artifactType)}/download`;
  const response = await fetch(
    endpoint,
  );
  if (!response.ok) {
    const payload = (await response.json().catch(() => null)) as GatewayError | null;
    throw new ApiError(
      payload && typeof payload.message === 'string'
        ? payload.message
        : '文书下载失败，请稍后重试',
      response.status,
    );
  }
  const disposition = response.headers.get('content-disposition') ?? '';
  const encoded = /filename\*=UTF-8''([^;]+)/i.exec(disposition)?.[1];
  const plain = /filename="?([^";]+)"?/i.exec(disposition)?.[1];
  let filename = artifactType === 'complaint'
    ? '要素式起诉状.docx'
    : artifactType === 'evidence_package'
      ? '证据材料包.zip'
      : '证据目录.docx';
  try {
    filename = encoded ? decodeURIComponent(encoded) : plain || filename;
  } catch {
    filename = plain || filename;
  }
  return { blob: await response.blob(), filename };
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
