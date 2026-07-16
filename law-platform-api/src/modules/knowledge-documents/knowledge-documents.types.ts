export interface KnowledgeDocumentSummary {
  doc_id: string;
  attachment_id: string;
  title: string;
  category: string;
  embedding_status: string;
  file_name: string;
  file_size: string | null;
  image_total: number;
  created_at: string;
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
  upload_timings: ProcessingTimings | null;
  ingest_timings: ProcessingTimings | null;
}

export interface KnowledgeDocumentSourceMutationResponse {
  document: KnowledgeDocumentSummary;
  source: KnowledgeDocumentSource;
  chunk_count: number;
}
