// ============================================================
// Public Types
// ============================================================

export interface ClaimListItem {
  claim_id: string;
  statement: string;
  status: string;
  claimant_id: string | null;
  declared_at: string | null;
  last_updated: string | null;
  ledger_integrity_valid: boolean;
}

export interface EvidenceItem {
  evidence_id: string;
  source_title: string;
  source_url: string;
  source_publisher: string | null;
  source_date: string | null;
  supports_claim: boolean | null;
  confidence_score: string | null;
  summary: string;
}

export interface TimelineEvent {
  seq: number;
  event_type: string;
  event_hash: string;
  prev_hash: string | null;
  created_at: string;
  event_id: string;
}

export interface ClaimDetail {
  claim_id: string;
  status: string;
  ledger_integrity_valid: boolean;
  declared: Record<string, unknown> | null;
  operationalized: Record<string, unknown> | null;
  resolved: Record<string, unknown> | null;
  evidence: EvidenceItem[];
  timeline: TimelineEvent[];
}

export interface IntegrityStatus {
  ledger_integrity_valid: boolean;
  event_count: number;
  last_event_hash: string | null;
}

// ============================================================
// Editor Types
// ============================================================

export interface LoginRequest {
  username: string;
  password: string;
}

export interface LoginResponse {
  success: boolean;
  username: string;
  editor_id: string;
  role: string;
}

export interface MeResponse {
  username: string;
  editor_id: string;
  role: string;
  ledger_integrity_valid: boolean;
  claim_count: number;
}

export interface DeclareRequest {
  statement: string;
  statement_context?: string;
  source_url?: string;
  claim_type?: string;
  geographic?: string;
  policy_domain?: string;
  affected_population?: string;
}

export interface OperationalizeRequest {
  claim_id: string;
  outcome_description: string;
  metrics: string[];
  direction_of_change?: string;
  baseline_value?: string;
  baseline_date?: string;
  start_date: string;
  evaluation_date: string;
  tolerance_window_days?: number;
  success_conditions: string[];
  partial_success_conditions?: string[];
  failure_conditions?: string[];
  notes?: string;
}

export interface EvidenceRequest {
  claim_id: string;
  source_url: string;
  source_title: string;
  source_publisher?: string;
  source_date?: string;
  source_type?: string;
  evidence_type?: string;
  summary: string;
  supports_claim?: boolean;
  relevance_explanation?: string;
  confidence_score?: string;
  confidence_rationale?: string;
}

export interface ResolveRequest {
  claim_id: string;
  resolution: string;
  resolution_summary: string;
  supporting_evidence_ids?: string[];
  resolution_details?: string;
}

export interface EventResponse {
  success: boolean;
  event_id: string;
  event_type: string;
  event_hash: string;
}

export interface EditorClaimListItem {
  claim_id: string;
  statement: string;
  status: string;
}

// ============================================================
// Auth Context Types
// ============================================================

export interface AuthState {
  isAuthenticated: boolean;
  user: MeResponse | null;
  loading: boolean;
}

