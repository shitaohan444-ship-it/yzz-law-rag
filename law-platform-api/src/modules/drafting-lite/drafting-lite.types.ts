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
  document_id?: string | number;
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
  document_id?: string | null;
  title: string;
  status: string;
}

export interface DraftingLiteMaterialSummary {
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
  items: DraftingLiteMaterialSummary[];
  total: number;
  page: number;
  page_size: number;
}
