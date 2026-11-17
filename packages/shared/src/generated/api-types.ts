// GENERATED FILE — DO NOT EDIT.
//
// Written by `pnpm gen:api` from:
//   docs/api/openapi.json
//
// Hand edits are discarded by the next `pnpm gen:api`. `pnpm gen:check`
// (part of `pnpm verify:web`) fails while this file disagrees with the
// contract. To change what is here, change the FastAPI route or Pydantic
// model and re-run `pnpm contract:export && pnpm gen:api`.

/** The benchmark in flight on this API process, if any (in-memory). */
export interface BenchmarkProgress {
  /** Report of the most recent run that finished on this process. */
  last_run_id: string | null;
  phase: string | null;
  running: boolean;
  started_at: string | null;
  tenant_id: string | null;
  /** The run's tenants, in order. */
  tenant_ids: string[];
  tenants_done: number;
  tenants_total: number;
}

export interface BenchmarkRequest {
  queries_per_phase?: number;
  tenant_ids: string[];
}

/** One day's upload count, for the dashboard activity chart. */
export interface DailyUploadCount {
  date: string;
  uploads: number;
}

/** Acknowledgement that one object was removed from the bucket. */
export interface DeleteFileResponse {
  deleted: boolean;
  key: string;
}

export interface DeleteTenantResult {
  collection_dropped: boolean;
  deleted_keys: string[];
}

/**
 * One text or Markdown document, sent as text (the browser reads the
 * file).
 */
export interface DocumentIn {
  filename: string;
  text: string;
}

export interface DocumentInfo {
  chunks: number;
  filename: string;
  /** B2 object key of the source document. */
  key: string;
  size_bytes: number;
}

/** One stored object as the file list and the by-key metadata route see it. */
export interface FileMetadata {
  content_type: string;
  filename: string;
  folder: string;
  key: string;
  size_bytes: number;
  size_human: string;
  uploaded_at: string;
  /**
   * Public object URL, set only when B2_PUBLIC_URL_BASE is configured and
   * the bucket is public. Null otherwise — the UI asks the API for a
   * proxied content URL instead.
   */
  url: string | null;
}

/** Checksums recomputed on demand by re-reading the stored object. */
export interface FileMetadataDetail {
  extension: string;
  filename: string;
  md5: string;
  mime_type: string;
  sha256: string;
  size_bytes: number;
  size_human: string;
  uploaded_at: string;
}

/**
 * Where the browser fetches one object's bytes, through this API. No
 * presigned B2 URL is ever handed to the browser: every byte goes through
 * the backend's S3 client, which carries the app's custom user agent.
 */
export interface FileUrlResponse {
  /**
   * API-relative URL of the content proxy (`/files-by-key/content`).
   * Download URLs ask for an attachment disposition; preview URLs ask for
   * inline so a PDF or text file renders in place.
   */
  url: string;
}

export interface HTTPValidationError {
  detail?: ValidationError[];
}

/**
 * Liveness plus B2 and Qdrant reachability. The route answers HTTP 200
 * even when a dependency is unreachable, so a caller must read
 * `b2_connected` and `qdrant.ok` rather than the status code.
 */
export interface HealthStatus {
  /** True when the bucket answered a cheap head request. */
  b2_connected: boolean;
  qdrant: QdrantHealth;
  /** "healthy" when B2 and Qdrant answered, else "degraded". */
  status: string;
}

export interface LatencyReport {
  created_at: string;
  embedding_model: string;
  qdrant_version: string | null;
  run_id: string;
  tenants: TenantLatency[];
}

export interface LatencyStats {
  mean_ms: number;
  n: number;
  p50_ms: number;
  p95_ms: number;
}

export interface LibraryEntry {
  key: string;
  kind: string;
  last_modified: string;
  size_bytes: number;
  tenant_id: string | null;
}

export interface MemoryFreed {
  /** Observed Qdrant resident-memory drop; null when the metric is absent. */
  node_rss_delta_bytes: number | null;
  vector_bytes_estimate: number;
}

export interface ParkResult {
  manifest: SnapshotManifest | null;
  /** Observed change in Qdrant resident memory; the allocator may lag. */
  node_rss_delta_bytes: number | null;
  reason: string | null;
  snapshot_upload_ms: number;
  state: string;
  tenant_id: string;
  /** Estimated hot-tier bytes released (0 if not parked). */
  vector_bytes_freed: number;
  verified: boolean;
}

export interface PruneRequest {
  apply?: boolean;
  keep_last?: number;
}

export interface PruneResult {
  applied: boolean;
  candidates: string[];
  deleted: string[];
  enabled: boolean;
}

/** Reachability of the hot tier. */
export interface QdrantHealth {
  /** True when the Qdrant node answered. */
  ok: boolean;
  /** Server version reported by the node. */
  version: string | null;
}

export interface QueryHit {
  chunk: number;
  doc: string;
  score: number;
  text: string;
}

export interface QueryRequest {
  query: string;
  top_k?: number;
}

export interface QueryResponse {
  hits: QueryHit[];
  /** Embedding plus vector search, excluding any restore. */
  latency_ms: number;
  restore: RestoreTiming | null;
  restored: boolean;
}

export interface ReportSummary {
  created_at: string;
  run_id: string;
  tenant_count: number;
}

export interface RestoreResult {
  point_count: number;
  state: string;
  tenant_id: string;
  timing: RestoreTiming;
}

export interface RestoreTiming {
  download_ms: number;
  load_ms: number;
  total_ms: number;
}

export interface SeedRequest {
  tenant_count?: number;
}

export interface SeedResult {
  created: string[];
  skipped: string[];
}

export interface SkippedTenant {
  reason: string;
  tenant_id: string;
}

export interface SnapshotEntry {
  created_at: string;
  is_latest: boolean;
  key: string;
  size_bytes: number;
}

/**
 * `rag/snapshots/<tenant>/latest.json`, written LAST in a park. Restore
 * trusts nothing else: the object key, its size and sha256, and the vector
 * configuration the points were embedded with.
 */
export interface SnapshotManifest {
  created_at: string;
  distance: string;
  embedding_model: string;
  /** Payload bytes recorded at ingest, for the memory estimate. */
  payload_bytes: number;
  point_count: number;
  qdrant_version: string | null;
  sha256: string;
  size_bytes: number;
  snapshot_id: string;
  snapshot_key: string;
  tenant_id: string;
  vector_size: number;
}

export interface TenantCreate {
  display_name: string;
  documents: DocumentIn[];
  /** Lowercase letters, digits and hyphens, 2 to 40 characters. */
  tenant_id: string;
}

export interface TenantDetail {
  created_at: string;
  display_name: string;
  document_count: number;
  documents: DocumentInfo[];
  /** In-memory; resets when the API restarts. */
  last_query_at: string | null;
  manifest: SnapshotManifest | null;
  point_count: number;
  snapshot_created_at: string | null;
  snapshot_size_bytes: number | null;
  /** True when documents changed after the latest snapshot was taken. */
  snapshot_stale: boolean;
  state: string;
  tenant_id: string;
  /** points * vector_size * 4 plus payload bytes: the hot-tier footprint. */
  vector_bytes_estimate: number;
}

export interface TenantLatency {
  first_query_after_restore_ms: number;
  memory_freed: MemoryFreed;
  point_count: number;
  post_restore: LatencyStats;
  restore: RestoreTiming;
  /** Post-restore hits equal warm hits (same ids, scores within 1e-4). */
  results_match: boolean;
  snapshot_bytes: number;
  snapshot_upload_ms: number;
  tenant_id: string;
  warm: LatencyStats;
}

/** What is running on a tenant right now (in memory; no B2 read). */
export interface TenantProgress {
  /** Units done in this stage (documents or chunks). */
  done: number | null;
  /** The stage in flight; null when idle. */
  state: string | null;
  tenant_id: string;
  total: number | null;
}

/** One row of the tenants table. State is derived, never stored. */
export interface TenantSummary {
  display_name: string;
  document_count: number;
  /** In-memory; resets when the API restarts. */
  last_query_at: string | null;
  point_count: number;
  snapshot_created_at: string | null;
  snapshot_size_bytes: number | null;
  state: string;
  tenant_id: string;
  /** points * vector_size * 4 plus payload bytes: the hot-tier footprint. */
  vector_bytes_estimate: number;
}

export interface TenantUpdate {
  add_documents?: DocumentIn[];
  display_name?: string | null;
  remove_documents?: string[];
}

export interface TieringPolicy {
  idle_seconds: number;
  prune_enabled: boolean;
  sweep_interval_seconds: number;
}

export interface TieringRunRequest {
  dry_run?: boolean;
  idle_seconds?: number | null;
}

export interface TieringRunResult {
  candidates: string[];
  dry_run: boolean;
  parked: string[];
  skipped: SkippedTenant[];
}

export interface TieringStats {
  corpus_bytes_b2: number;
  empty: number;
  hot: number;
  parked: number;
  snapshot_bytes_b2: number;
  vector_bytes_freed: number;
  vector_bytes_hot: number;
}

/** Aggregate bucket figures behind the dashboard stat cards. */
export interface UploadStats {
  total_downloads: number;
  total_files: number;
  total_size_bytes: number;
  total_size_human: string;
  uploads_today: number;
}

export interface ValidationError {
  ctx?: Record<string, unknown>;
  input?: unknown;
  loc: (string | number)[];
  msg: string;
  type: string;
}
