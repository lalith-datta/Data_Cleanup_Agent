export interface Run {
  id: number;
  name: string;
  status: string;
  config_json: Record<string, unknown>;
  stats_json: RunStats;
  created_at: string;
  updated_at: string;
}

export interface RunStats {
  records: number;
  valid: number;
  needs_review: number;
  pushed: number;
  push_failed: number;
  auto_mappings: number;
  auto_cleans: number;
  llm_mappings: number;
  escalations_open: number;
  escalations_resolved: number;
  stp_rate: number;
}

export interface SourceFile {
  id: number;
  run_id: number;
  filename: string;
  entity: string;
  row_count: number;
  columns_json: string[];
  stored_path: string;
  uploaded_at: string;
}

export interface ActivityEvent {
  id: number;
  ts: string;
  stage: string;
  message: string;
}

export interface Escalation {
  id: number;
  run_id: number;
  type:
    | "ambiguous_mapping"
    | "value_conflict"
    | "ambiguous_date"
    | "validation_failure"
    | "unmapped_column"
    | "manager_unresolved";
  entity_ref: string;
  context_json: Record<string, any>;
  options_json: Array<Record<string, any>>;
  confidence: number;
  status: "open" | "resolved" | "rejected";
  resolution_json: Record<string, any>;
  resolved_by: string | null;
  resolved_at: string | null;
  created_at: string;
}

export interface RecordRow {
  id: number;
  run_id: number;
  natural_key: string;
  merged_json: Record<string, string | null>;
  source_refs_json: Record<string, { file: string; raw: unknown }>;
  status: string;
  created_at: string;
  updated_at: string;
}

export interface AuditEntry {
  id: number;
  run_id: number;
  ts: string;
  actor: "agent" | "human";
  action: string;
  target_type: string;
  target_id: string;
  before_json: Record<string, any>;
  after_json: Record<string, any>;
  reason: string;
}

export const ESCALATION_LABELS: Record<string, string> = {
  ambiguous_mapping: "Ambiguous mapping",
  value_conflict: "Conflicting values",
  ambiguous_date: "Ambiguous date",
  validation_failure: "Validation failure",
  unmapped_column: "Unmapped column",
  manager_unresolved: "Manager lookup",
};
