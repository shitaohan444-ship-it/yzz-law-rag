export interface RagOfficialLink {
  provider: 'npc_flk';
  source_name: '国家法律法规数据库';
  label: '官网最新版';
  url: string;
}

export interface RagHit {
  chunk_id: string;
  doc_id: number;
  doc_title: string | null;
  source: string;
  chunk_idx: number;
  text: string;
  score: number;
  article_no?: string | null;
  chapter?: string | null;
  content_type?: string;
  image_id?: number | null;
  page_no?: number | null;
  image_category?: string | null;
  category_id?: number | null;
  category_path?: string[] | null;
  official_link?: RagOfficialLink | null;
}

export interface RagSearchResponse {
  query: string;
  total: number;
  hits: RagHit[];
}

export interface RagChatRef extends RagHit {
  ref_id: number;
}

export interface RagChatResponse {
  question: string;
  answer: string;
  refs: RagChatRef[];
  chat_log_id: number | null;
  hits_count: number;
}

export interface RagIngestResponse {
  doc_id: number;
  status: string;
  chunk_count: number;
  image_total: number;
  image_kept: number;
  image_filtered: number;
  vl_status: string;
  message: string;
  error_code?: string | null;
  request_id: string;
  upload_timings: RagProcessingTimings | null;
  ingest_timings: RagProcessingTimings | null;
}

export interface RagProcessingTimings {
  version: number;
  status: string;
  started_at: string;
  completed_at: string;
  total_ms: number;
  stages: Array<{
    key: string;
    label: string;
    elapsed_ms: number;
    status: string;
  }>;
}

export interface RagDocumentStatus {
  doc_id: number;
  embedding_status: string;
  chunk_count: number;
  doc_title: string | null;
  vl_status: string;
  image_total: number;
  image_kept: number;
  image_filtered: number;
  vl_processed_at: string | null;
  error_code?: string | null;
  request_id: string;
  upload_timings: RagProcessingTimings | null;
  ingest_timings: RagProcessingTimings | null;
}

export interface RagDocumentMarkdown {
  doc_id: number;
  doc_title: string | null;
  description_summary: string | null;
  image_count: number;
  markdown: string;
  request_id: string;
}

export interface RagDocumentChunk {
  chunk_id: string;
  chunk_idx: number;
  text: string;
  char_count: number;
  source: string | null;
  article_no: string | null;
  chapter: string | null;
  content_type: string | null;
  image_id: number | null;
  page_no: number | null;
  image_category: string | null;
}

export interface RagDocumentChunks {
  doc_id: number;
  doc_title: string | null;
  total: number;
  page: number;
  page_size: number;
  items: RagDocumentChunk[];
  request_id: string;
}

export interface RagSourcePromotionResponse {
  doc_id: number;
  source_id: number;
  status: string;
  source_chunk_count: number;
  chunk_count: number;
  image_total: number;
  request_id: string;
  upload_timings: RagProcessingTimings | null;
  ingest_timings: RagProcessingTimings | null;
}

export interface RagVerifyRestoreItem {
  doc_id: number;
  ok: boolean;
  missing_chunks: number;
  missing_images: string[];
}

export interface RagVerifyRestoreResponse {
  items: RagVerifyRestoreItem[];
  request_id: string;
}
