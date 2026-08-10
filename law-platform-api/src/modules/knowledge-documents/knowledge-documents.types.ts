export interface KnowledgeDocumentSummary {
  doc_id: string;
  attachment_id: string;
  title: string;
  category: string;
  category_id: string;
  category_name: string;
  category_path: string[];
  category_path_ids: string[];
  category_sensitive: boolean;
  embedding_status: string;
  file_name: string;
  file_size: string | null;
  image_total: number;
  created_at: string;
  last_uploaded_at: string;
  upload_timings: ProcessingTimings | null;
  ingest_timings: ProcessingTimings | null;
  source_count: number;
}

export interface ProcessingTimingStage {
  key: string;
  label: string;
  elapsed_ms: number;
  status: 'success' | 'failed' | 'skipped';
}

export interface ProcessingTimings {
  version: 1;
  status: 'success' | 'failed';
  started_at: string;
  completed_at: string;
  total_ms: number;
  stages: ProcessingTimingStage[];
}

export interface KnowledgeDocumentUploadResponse {
  document: KnowledgeDocumentSummary;
  deduplicated: boolean;
}

export interface KnowledgeDocumentReplaceResponse {
  document: KnowledgeDocumentSummary;
  chunk_count: number;
  replaced: true;
  request_id: string;
}

export interface KnowledgeDocumentSource {
  source_id: string;
  document_id: string;
  attachment_id: string;
  source_title: string;
  file_name: string;
  file_size: string | null;
  sort_order: number;
  is_primary: boolean;
  ingest_status: string;
  chunk_count: number;
  image_total: number;
  uploaded_at: string;
  upload_timings: ProcessingTimings | null;
  ingest_timings: ProcessingTimings | null;
}

export interface KnowledgeDocumentSourceMutationResponse {
  document: KnowledgeDocumentSummary;
  source: KnowledgeDocumentSource;
  chunk_count: number;
  request_id: string;
}

export interface KnowledgeDocumentBatchMoveResponse {
  moved: number;
  category_id: string;
  category_path: string[];
}

export interface KnowledgeDocumentBatchDeleteResponse {
  deleted: number;
  mode: 'soft';
  artifacts_retained: true;
}

export interface TrashDocumentSummary {
  doc_id: string;
  attachment_id: string;
  title: string;
  category_id: string | null;
  category_name: string | null;
  category_path: string[] | null;
  category_path_ids: string[] | null;
  category_valid: boolean;
  restorable: boolean;
  deleted_at: string;
  file_name: string;
  file_size: string | null;
  source_count: number;
  embedding_status: string;
}

export interface TrashListResponse {
  items: TrashDocumentSummary[];
  total: number;
  page: number;
  page_size: number;
}

export interface KnowledgeDocumentBatchRestoreResponse {
  restored: number;
  doc_ids: string[];
  request_id: string;
}

export interface KnowledgeDocumentBatchPurgeResponse {
  purged: number;
  already_purged: number;
  request_id?: string;
}
