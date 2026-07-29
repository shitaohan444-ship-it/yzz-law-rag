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
}

export interface SearchResponse {
  query: string;
  total: number;
  hits: RagHit[];
}

export interface ChatRef extends RagHit {
  ref_id: number;
}

export interface ChatResponse {
  question: string;
  answer: string;
  refs: ChatRef[];
  chat_log_id: number | null;
  hits_count: number;
}

export type DraftingLiteStatus =
  | 'queued'
  | 'parsing'
  | 'matching_cause'
  | 'waiting_cause_selection'
  | 'waiting_party_confirmation'
  | 'retrieving_laws'
  | 'drafting'
  | 'rendering'
  | 'completed'
  | 'failed';

export interface DraftingLiteJob {
  job_id: string;
  status: DraftingLiteStatus;
  progress: number;
  current_agent: string;
  cause_requested: string;
  cause_code: string | null;
  cause_label: string | null;
  confidence: number | null;
  template_name: string | null;
  cause_evidence: Array<{
    file_name?: string;
    page_no?: number | null;
    reason?: string;
    document_id?: number | string;
    chunk_id?: string;
  }>;
  party_extraction: PartyExtractionResult | null;
  party_issues: PartyIssue[];
  party_confirmation_required: boolean;
  party_input_version: number;
  warnings: string[];
  error_message: string | null;
  download_url: string | null;
  created_at: string;
  updated_at: string;
  input_mode?: 'upload' | 'knowledge' | 'mixed';
  selected_materials?: DraftingLiteSelectedMaterial[];
}

export interface PartySource {
  source_type: 'material' | 'user';
  file_name?: string;
  page_no?: number | null;
  document_id?: number | string;
  chunk_id?: string;
  note?: string;
  derived_from?: string;
}

export interface PartyRecord {
  party_id: string;
  role: 'plaintiff' | 'defendant' | 'third_party' | 'unknown';
  entity_type: 'natural_person' | 'organization' | 'unknown';
  name?: string | null;
  gender?: string | null;
  birth_date?: string | null;
  ethnicity?: string | null;
  phone?: string | null;
  address?: string | null;
  current_address?: string | null;
  id_type?: string | null;
  id_number?: string | null;
  organization_name?: string | null;
  organization_address?: string | null;
  organization_registration_address?: string | null;
  organization_phone?: string | null;
  unified_social_credit_code?: string | null;
  legal_representative?: string | null;
  field_provenance: Record<string, PartySource[]>;
  field_conflicts: Record<string, Array<{ value: unknown; sources: PartySource[] }>>;
}

export interface PartyExtractionResult {
  schema_version: string;
  parties: PartyRecord[];
  warnings: string[];
  issues?: PartyIssue[];
  audit_history?: Array<{ source: string; parties: PartyRecord[] }>;
}

export interface PartyIssue {
  code: string;
  message: string;
  party_id?: string;
  role?: string;
  field?: string;
  candidates?: Array<{ value: unknown; sources: PartySource[] }>;
}

export interface DraftingLiteCause {
  code: string;
  label: string;
  template_name: string;
}

export interface DraftingLiteSelectedMaterial {
  source_kind: 'upload' | 'knowledge';
  document_id?: number | string | null;
  title: string;
  status: string;
}

export interface DraftingLiteMaterial {
  document_id: string;
  title: string;
  file_name: string;
  category_path: string[];
  embedding_status: string;
  last_uploaded_at: string;
  source_count: number;
  image_total: number;
}

export interface DraftingLiteMaterialList {
  items: DraftingLiteMaterial[];
  total: number;
  page: number;
  page_size: number;
}

export interface KnowledgeCategoryNode {
  id: string;
  code: string;
  name: string;
  aliases: string[];
  parent_id: string | null;
  path: string[];
  path_ids: string[];
  depth: number;
  sort_order: number;
  assignable: boolean;
  sensitive: boolean;
  effective_sensitive: boolean;
  is_system: boolean;
  status: 'active' | 'inactive';
  direct_document_count: number;
  total_document_count: number;
  children: KnowledgeCategoryNode[];
}

export interface KnowledgeCategoryTreeResponse {
  items: KnowledgeCategoryNode[];
}

export interface ProcessingTimingStage {
  key: string;
  label: string;
  elapsed_ms: number;
  status: 'success' | 'failed' | 'skipped';
}

export interface ProcessingTimings {
  version: number;
  status: string;
  started_at: string;
  completed_at: string;
  total_ms: number;
  stages: ProcessingTimingStage[];
}

export interface KnowledgeDocument {
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

export interface KnowledgeDocumentUploadResponse {
  document: KnowledgeDocument;
  deduplicated: boolean;
}

export interface KnowledgeDocumentReplaceResponse {
  document: KnowledgeDocument;
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
  uploaded_at: string;
  upload_timings: ProcessingTimings | null;
  ingest_timings: ProcessingTimings | null;
}

export interface KnowledgeDocumentSourcesResponse {
  items: KnowledgeDocumentSource[];
}

export interface KnowledgeDocumentSourceMutationResponse {
  document: KnowledgeDocument;
  source: KnowledgeDocumentSource;
  chunk_count: number;
}

export interface KnowledgeDocumentListResponse {
  items: KnowledgeDocument[];
  total: number;
  page: number;
  page_size: number;
}

export interface KnowledgeDocumentStatus {
  doc_id: number;
  embedding_status: string;
  chunk_count: number;
  doc_title: string | null;
  vl_status: string;
  image_total: number;
  image_kept: number;
  image_filtered: number;
  vl_processed_at: string | null;
  upload_timings: ProcessingTimings | null;
  ingest_timings: ProcessingTimings | null;
}

export interface KnowledgeIngestResponse {
  doc_id: number;
  status: string;
  chunk_count: number;
  image_total: number;
  image_kept: number;
  image_filtered: number;
  vl_status: string;
  message: string;
  upload_timings: ProcessingTimings | null;
  ingest_timings: ProcessingTimings | null;
}

export interface KnowledgeDocumentMarkdown {
  doc_id: number;
  doc_title: string | null;
  description_summary: string | null;
  image_count: number;
  markdown: string;
  source_count: number;
  source_id: number | null;
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

export interface TrashDocument {
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
  items: TrashDocument[];
  total: number;
  page: number;
  page_size: number;
}

export interface KnowledgeDocumentBatchRestoreResponse {
  restored: number;
  doc_ids: string[];
}

export interface KnowledgeDocumentBatchPurgeResponse {
  purged: number;
  already_purged: number;
}

export interface KnowledgeDocumentChunk {
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
  source_id: number | null;
  source_title: string | null;
  source_file_name: string | null;
  source_chunk_idx: number | null;
}

export interface KnowledgeDocumentChunks {
  doc_id: number;
  doc_title: string | null;
  total: number;
  page: number;
  page_size: number;
  items: KnowledgeDocumentChunk[];
}
