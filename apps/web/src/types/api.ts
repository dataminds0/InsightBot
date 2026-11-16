/** TypeScript interfaces representing InsightBot API contracts */

export interface User {
  user_id: string;
  username: string;
  email?: string | null;
  role: "Viewer" | "Analyst" | "Admin" | "Worker" | string;
  status: "Active" | "Pending" | "Disabled" | string;
}

export interface LoginResponse {
  user: User;
  token: string;
}

export interface ArticleListItem {
  article_id: string;
  source_id: string;
  canonical_url: string;
  title: string;
  language: string;
  published_at?: string | null;
  publication_date_unknown_reason?: string | null;
  fetched_at: string;
  current_version: number;
  stage_states?: Record<string, string>;
  quarantine_reason?: string | null;
  word_count?: number;
  reading_time_minutes?: number;
}

export interface ArticleDetail {
  article_id: string;
  source_id: string;
  canonical_url: string;
  original_url: string;
  resolved_url: string;
  title: string;
  body_text: string;
  content_hash: string;
  language: string;
  published_at?: string | null;
  publication_date_unknown_reason?: string | null;
  fetched_at: string;
  first_seen_at: string;
  updated_at: string;
  current_version: number;
  fencing_token: number;
  stage_states?: Record<string, string>;
  quarantine_reason?: string | null;
  word_count?: number;
  reading_time_minutes?: number;
  extra_metadata?: Record<string, unknown>;
}

export interface ArticleVersionItem {
  article_id: string;
  version: number;
  title: string;
  body_text: string;
  content_hash: string;
  operation: string;
  created_at: string;
  raw_storage_key?: string | null;
}

export interface ArticleListResponse {
  items: ArticleListItem[];
  total_count: number;
  limit: number;
  next_cursor?: string | null;
}

export interface SourcePolicy {
  rate_limit_per_minute: number;
  retention_days: number;
  allow_raw_storage: boolean;
  owner: string;
}

export interface Source {
  source_id: string;
  name: string;
  url: string;
  feed_urls: string[];
  language: string;
  enabled: boolean;
  policy: SourcePolicy;
  created_at: string;
  updated_at: string;
  extra_config?: Record<string, unknown>;
}

export interface Capabilities {
  version: string;
  languages: string[];
  rtl_languages: string[];
  search_engine: string;
  nlp_enabled: boolean;
  assistant_enabled: boolean;
  max_page_limit: number;
}

export interface ApiErrorDetail {
  code: string;
  message: string;
  request_id?: string;
  details?: unknown;
}

export interface SourceHealthItem {
  source_id: string;
  name: string;
  url: string;
  language: string;
  enabled: boolean;
  rate_limit_per_minute: number;
  retention_days: number;
  total_articles: number;
  latest_fetched_at?: string | null;
  latest_published_at?: string | null;
  failed_jobs_count: number;
  recent_error?: string | null;
}

export interface Job {
  job_id: string;
  kind: string;
  target_id: string;
  status: string;
  attempts: number;
  max_attempts: number;
  error?: string | null;
  created_at: string;
  updated_at: string;
  payload?: Record<string, unknown>;
  result_data?: Record<string, unknown>;
}

export interface JobRunsResponse {
  jobs: Job[];
  stats: Record<string, number>;
}

export interface AuditLog {
  log_id: string;
  actor_id: string;
  action: string;
  entity_type: string;
  entity_id: string;
  details: Record<string, unknown>;
  created_at: string;
}

export interface Bookmark {
  bookmark_id: string;
  user_id: string;
  article_id: string;
  notes?: string | null;
  tags: string[];
  created_at: string;
}

export interface BookmarkItem extends Bookmark {
  target_available: boolean;
  article?: ArticleListItem | null;
}

export interface BookmarkListResponse {
  items: BookmarkItem[];
  total: number;
  skip: number;
  limit: number;
}

export interface SavedQuery {
  query_id: string;
  user_id: string;
  name: string;
  query_params: Record<string, unknown>;
  alerts_enabled: boolean;
  created_at: string;
  updated_at: string;
}

export interface SavedQueryListResponse {
  items: SavedQuery[];
  total: number;
  skip: number;
  limit: number;
}

export interface PrivateNote {
  note_id: string;
  user_id: string;
  article_id: string;
  content: string;
  created_at: string;
  updated_at: string;
}

export interface NoteItem extends PrivateNote {
  target_available: boolean;
  article?: ArticleListItem | null;
}

export interface NoteListResponse {
  items: NoteItem[];
  total: number;
  skip: number;
  limit: number;
}
