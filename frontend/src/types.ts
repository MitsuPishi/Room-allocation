export type Session = {
  username: string;
  must_change_password: boolean;
  csrf_token: string;
};

export type Dataset = {
  id: string;
  original_filename: string;
  row_count: number;
  is_valid: boolean;
  error_count: number;
  warning_count: number;
  validation_issues: Array<Record<string, unknown>>;
  created_at: string;
};

export type CapacityEntry = { count: number; capacity: number };

export type RunConfiguration = {
  capacity_mode: "uniform" | "mixed";
  capacity: number | null;
  capacity_mix: CapacityEntry[];
  time_limit_seconds: number;
  seed: number;
  restarts: number;
  cp_sat_enabled: boolean;
};

export type Run = {
  id: string;
  dataset_id: string;
  dataset_filename: string;
  student_count: number;
  status: "draft" | "queued" | "running" | "succeeded" | "failed" | "cancelled";
  configuration: RunConfiguration;
  scoring_configuration: Record<string, unknown>;
  progress: Record<string, unknown>;
  metrics: Record<string, number> | null;
  metadata: Record<string, any> | null;
  artifacts: Record<string, { size: number; sha256: string; storage_key: string }>;
  error_message: string | null;
  cancel_requested: boolean;
  created_at: string;
  queued_at: string | null;
  started_at: string | null;
  completed_at: string | null;
  runtime_seconds: number | null;
};

export type Page<T = Record<string, unknown>> = {
  items: T[];
  total: number;
  offset: number;
  limit: number;
};
