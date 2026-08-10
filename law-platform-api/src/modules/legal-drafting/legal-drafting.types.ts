export const GENERATION_RUN_STATUSES = [
  'pending',
  'claimed',
  'running',
  'waiting_template_confirmation',
  'waiting_user_input',
  'reviewing',
  'rewriting',
  'rendering',
  'pending_lawyer_review',
  'approved',
  'returned',
  'failed',
  'cancelled',
] as const;

export type GenerationRunStatus = (typeof GENERATION_RUN_STATUSES)[number];

export const TERMINAL_RUN_STATUSES = new Set<GenerationRunStatus>([
  'approved',
  'returned',
  'failed',
  'cancelled',
]);

export interface RunEventInput {
  eventSeq: number;
  eventType: string;
  status?: GenerationRunStatus;
  currentNode?: string;
  progress?: number;
  payload?: Record<string, unknown>;
  errorCode?: string;
  errorMessage?: string;
}

export interface RunTokenPayload {
  runId: string;
  caseId: string;
  materialIds: string[];
  evidenceIds: string[];
  knowledgeDocumentIds: string[];
  expiresAt: string;
}
