export interface OfficialLink {
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
  official_link?: OfficialLink | null;
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

export interface LegalTemplateMatch {
  template_id: string;
  template_version_id: string;
  template_code: string;
  template_name: string;
  confidence: number;
  requires_confirmation: boolean;
}

export interface LegalTemplateMatchResponse {
  items: LegalTemplateMatch[];
}

export interface LegalDraftingMissingElement {
  field_id: string;
  label: string;
  missing_behavior?: string;
  checked_sources?: string[];
}

export interface LegalDraftingConflict {
  field_id: string;
  label?: string;
  message?: string;
  conflict_type?: string;
  candidates?: Array<Record<string, unknown>>;
}

export interface LegalDraftingIssue {
  id?: string;
  issue_code: string;
  review_type: string;
  severity: string;
  field_id?: string;
  message: string;
}

export interface LegalDraftingEvent {
  event_seq: string;
  event_type: string;
  payload_json: Record<string, unknown>;
  created_at: string;
}

export interface LegalDraftingSource {
  id: string;
  field_id?: string | null;
  section_id?: string | null;
  source_type: string;
  material_id?: string | null;
  evidence_id?: string | null;
  knowledge_document_id?: string | null;
  chunk_id?: string | null;
  attachment_id?: string | null;
  page_no?: number | null;
  quote_text?: string | null;
}

export interface LegalDocumentVersion {
  id: string;
  version_no: number;
  version_kind: string;
  version_status: string;
  created_at: string;
  structured_content_json?: Record<string, unknown> | null;
}

export interface LegalDocumentVersionResponse {
  items: LegalDocumentVersion[];
}

export interface LegalDraftingRun {
  id: string;
  case_id: string;
  run_status: string;
  current_node: string | null;
  progress: number;
  input_version: number | string;
  template_name?: string | null;
  waiting_reason?: {
    missing_elements?: LegalDraftingMissingElement[];
    conflicts?: LegalDraftingConflict[];
    review_issues?: LegalDraftingIssue[];
    type?: string;
    comment?: string;
  } | null;
  result_document_id?: string | null;
  result_version_id?: string | null;
  docx_attachment_id?: string | null;
  pdf_attachment_id?: string | null;
  result_version_status?: string | null;
  error_code?: string | null;
  error_message?: string | null;
  issues?: LegalDraftingIssue[];
  sources?: LegalDraftingSource[];
  events?: LegalDraftingEvent[];
  structured_content_json?: Record<string, unknown> | null;
  provenance_json?: Record<string, unknown> | null;
  audit_report_json?: Record<string, unknown> | null;
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
  | 'drafting_evidence'
  | 'rendering_evidence'
  | 'collecting_evidence_media'
  | 'packaging_evidence'
  | 'completed'
  | 'cancelled'
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
  cause_candidates: Array<{
    cause_code: string;
    label: string;
    confidence: number;
  }>;
  party_extraction: PartyExtractionResult | null;
  party_issues: PartyIssue[];
  party_confirmation_required: boolean;
  party_input_version: number;
  warnings: string[];
  evidence_package_status?: 'generated' | 'partial' | null;
  evidence_package_issues?: string[];
  error_message: string | null;
  download_url: string | null;
  artifacts?: DraftingLiteArtifact[];
  created_at: string;
  updated_at: string;
  input_mode?: 'upload' | 'knowledge' | 'mixed';
  selected_materials?: DraftingLiteSelectedMaterial[];
}

export interface DraftingLiteArtifact {
  type: 'complaint' | 'evidence_directory' | 'evidence_package';
  filename: string;
  download_url: string;
}

export interface PartySource {
  source_type: 'material' | 'user' | 'computed';
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

export interface KnowledgeDocumentSourcesResponse {
  items: KnowledgeDocumentSource[];
}

export interface KnowledgeDocumentSourceMutationResponse {
  document: KnowledgeDocument;
  source: KnowledgeDocumentSource;
  chunk_count: number;
  request_id: string;
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
  error_code?: string | null;
  request_id: string;
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
  error_code?: string | null;
  request_id: string;
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
  request_id: string;
}

export interface KnowledgeDocumentBatchPurgeResponse {
  purged: number;
  already_purged: number;
  request_id?: string;
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
