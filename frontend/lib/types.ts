/** Shapes returned by the OriginLens API. Mirrors backend/app/api/schemas.py. */

export type AnalysisStatus = "queued" | "running" | "completed" | "failed";
export type Reliability = "insufficient" | "low" | "moderate" | "normal";

export interface ApiErrorBody {
  error: { code: string; message: string; correlation_id: string; fields?: string[] };
}

export interface Segment {
  id: string;
  index: number;
  text: string | null;
  word_count: number;
  character_count: number;
  public_score: number | null;
  raw_model_score: number | null;
  label: string | null;
  too_short: boolean;
  grouped_with_context: boolean;
}

export interface IntegrityWarning {
  code: string;
  message: string;
}

export interface Analysis {
  id: string;
  status: AnalysisStatus;
  source: "text" | "document";
  source_filename: string | null;
  created_at: string;
  completed_at: string | null;
  label: string | null;
  public_score: number | null;
  raw_model_score: number | null;
  reliability: Reliability | null;
  reliability_reasons: string[];
  counts: { words: number; characters: number; paragraphs: number };
  detected_language: string | null;
  language_confidence: number | null;
  window_stability: number | null;
  segments: Segment[];
  integrity_warnings: IntegrityWarning[];
  diagnostics: Record<string, unknown> | null;
  model_metadata: Record<string, unknown> | null;
  calibration_version: string | null;
  detector_version: string | null;
  failure_code: string | null;
  guest_token: string | null;
  stored_original_text: boolean;
  disclaimers: string[];
}

export interface AnalysisSummary {
  id: string;
  status: AnalysisStatus;
  source: "text" | "document";
  source_filename: string | null;
  created_at: string;
  label: string | null;
  public_score: number | null;
  reliability: Reliability | null;
  word_count: number;
}

export interface Paged<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export interface UserProfile {
  id: string;
  email: string;
  role: "user" | "admin";
  status: "pending" | "active" | "suspended";
  email_verified_at: string | null;
  created_at: string;
}

/** Answer to "who am I". `user` is null when nobody is signed in. */
export interface SessionResponse {
  user: UserProfile | null;
}

export interface Band {
  lower: number;
  upper: number;
  label: string;
}

export interface PublicConfig {
  product_name: string;
  tagline: string;
  support_email: string;
  min_words: number;
  low_reliability_words: number;
  max_words: number;
  max_characters: number;
  max_upload_bytes: number;
  allowed_extensions: string[];
  bands: Band[];
  disclaimers: string[];
  guest_retention_hours: number;
}

export interface AdminUser {
  id: string;
  email: string;
  role: string;
  status: string;
  created_at: string;
  last_login_at: string | null;
  suspended_at: string | null;
  suspension_reason: string | null;
}

export interface AdminStats {
  users_total: number;
  users_active: number;
  users_suspended: number;
  analyses_total: number;
  analyses_completed: number;
  analyses_failed: number;
  analyses_last_24h: number;
  feedback_total: number;
}

export interface ModelHealth {
  backend: string;
  is_real_model: boolean;
  loaded: boolean;
  load_error_code: string | null;
  load_error_detail: string | null;
  model: Record<string, unknown> | null;
}
