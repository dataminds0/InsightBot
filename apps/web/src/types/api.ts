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

export interface DuplicateEvidence {
  content_hash_match: boolean;
  jaccard_similarity: number;
  headline_similarity: number;
  shared_wire_agency?: string | null;
  differing_numbers_found: string[];
  temporal_delta_hours: number;
  reason: string;
  extra_data?: Record<string, unknown>;
}

export interface DuplicateRelationshipItem {
  relationship_id: string;
  is_canonical: boolean;
  duplicate_type: "exact_hash" | "syndication" | "near_duplicate" | string;
  status: "confirmed" | "flagged" | "rejected" | string;
  similarity_score: number;
  evidence: DuplicateEvidence;
  detected_at: string;
  related_article?: {
    article_id: string;
    source_id: string;
    title: string;
    canonical_url: string;
    published_at?: string | null;
    language: string;
    word_count?: number;
    reading_time_minutes?: number;
  } | null;
}

export interface StoryItem {
  story_id: string;
  title: string;
  summary: string;
  status: "emerging" | "peak" | "declining" | "closed" | string;
  lead_article_id: string;
  article_ids: string[];
  sources: string[];
  article_count: number;
  sources_count: number;
  first_article_at: string;
  last_article_at: string;
  created_at: string;
  updated_at: string;
  peak_at?: string | null;
  closed_at?: string | null;
  primary_location?: string | null;
  keywords: string[];
  entities: string[];
  version: number;
}

export interface StoryDetail extends StoryItem {
  member_articles: Array<{
    article_id: string;
    source_id: string;
    canonical_url: string;
    title: string;
    language: string;
    published_at?: string | null;
    fetched_at: string;
    word_count?: number;
    reading_time_minutes?: number;
  }>;
}

export interface StoryAuditItem {
  audit_id: string;
  story_id: string;
  action:
    | "created"
    | "article_added"
    | "article_removed"
    | "merged"
    | "split"
    | "status_changed"
    | "manual_edit"
    | string;
  actor_id: string;
  reason: string;
  details: Record<string, unknown>;
  timestamp: string;
}

export interface StoryListResponse {
  items: StoryItem[];
  total: number;
  next_cursor?: string | null;
}

export interface SearchResultItem {
  article_id: string;
  source_id: string;
  canonical_url: string;
  title: string;
  language: string;
  published_at?: string | null;
  fetched_at: string;
  word_count?: number;
  reading_time_minutes?: number;
  score: number;
  lexical_rank?: number | null;
  vector_rank?: number | null;
  rrf_score?: number | null;
  snippet: string;
}

export interface SearchResponse {
  items: SearchResultItem[];
  total: number;
  search_mode: "auto" | "hybrid" | "lexical" | "basic" | "basic_fallback" | string;
  index_generation: string;
  index_lag_seconds: number;
  fallback_reason?: string | null;
  query: string;
  as_of: string;
  next_cursor?: string | null;
}

export interface SearchStatusResponse {
  has_active_generation: boolean;
  active_generation?: {
    generation_id: string;
    is_active: boolean;
    article_count: number;
    chunks_count: number;
    vector_dimensions: number;
    created_at: string;
    activated_at?: string | null;
    status: string;
  } | null;
  index_lag_seconds: number;
  supported_modes: string[];
}

// Event Comparison (Task T16)
export interface TimelineMilestone {
  milestone_id: string;
  timestamp?: string | null;
  timestamp_basis: "published_at" | "fetched_at" | "unknown" | string;
  source_id: string;
  article_id: string;
  version: number;
  title: string;
  language: string;
  lead_quote: string;
  is_lead_article: boolean;
}

export interface SourcePerspective {
  source_id: string;
  article_count: number;
  first_reported_at?: string | null;
  first_reported_basis: string;
  latest_reported_at?: string | null;
  headline: string;
  lead_article_id: string;
  lead_article_version: number;
  key_entities: string[];
  framing_terms: string[];
  numerical_claims: string[];
  word_count: number;
  reading_time_minutes: number;
  latency_minutes_from_first: number;
}

export interface AttributedDifference {
  difference_id: string;
  category: "numerical_facts" | "named_entities" | "framing_language" | "timeline_latency" | string;
  description: string;
  source_a: string;
  source_a_claim: string;
  source_a_citation: string;
  source_b: string;
  source_b_claim: string;
  source_b_citation: string;
  severity: "high" | "medium" | "low" | string;
}

export interface VersionedEvidence {
  evidence_id: string;
  article_id: string;
  version: number;
  source_id: string;
  canonical_url: string;
  exact_quote: string;
  published_at?: string | null;
  context_title: string;
}

export interface AnalystReview {
  review_id: string;
  story_id: string;
  reviewer_id: string;
  status: "verified" | "flagged" | "in_dispute" | string;
  notes: string;
  excluded_article_ids: string[];
  reviewed_at: string;
}

export interface EventComparisonReport {
  story_id: string;
  story_title: string;
  story_status: "emerging" | "peak" | "declining" | "closed" | string;
  created_at: string;
  sources_count: number;
  articles_count: number;
  timeline: TimelineMilestone[];
  perspectives: SourcePerspective[];
  divergent_points: AttributedDifference[];
  evidence_items: VersionedEvidence[];
  latest_review?: AnalystReview | null;
  first_reported_source?: string | null;
  reporting_span_hours: number;
}

export interface ReviewStoryRequest {
  status: "verified" | "flagged" | "in_dispute" | string;
  notes: string;
  excluded_article_ids?: string[];
}
