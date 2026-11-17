"use client";

import {
  useMutation,
  useQuery,
  useQueryClient,
  type QueryClient,
} from "@tanstack/react-query";
import {
  ApiError,
  createTenant,
  deleteFile,
  deleteTenant,
  getDownloadUrl,
  getFileDetail,
  getFiles,
  getFileStats,
  getHealth,
  getPreviewUrl,
  getReport,
  getTenant,
  getTieringPolicy,
  getTieringStats,
  getUploadActivity,
  listLibrary,
  listReports,
  listTenants,
  listTenantSnapshots,
  parkTenant,
  pruneSnapshots,
  queryTenant,
  restoreTenant,
  runBenchmark,
  runTiering,
  seedTenants,
  updateTenant,
} from "@/lib/api-client";
import type {
  BenchmarkRequest,
  FileMetadata,
  FileMetadataDetail,
  FileUrlResponse,
  LatencyReport,
  PruneRequest,
  QueryRequest,
  QueryResponse,
  TenantCreate,
  TenantDetail,
  TenantUpdate,
  TieringRunRequest,
} from "@qdrant-multitenant-rag-tiering/shared";
import { qk } from "@/lib/generated/query-keys";

// Query keys are GENERATED from the API contract (`pnpm gen:api`) and their
// hierarchy is declared in `scripts/gen/api-gen.config.json`, so invalidating
// a parent key still reaches its children and no hook can invent a key the API
// cannot answer. Re-exported here because this module is the data layer's
// public surface: components and tests import `qk` from `@/lib/queries`.
//
// The caching policy below — staleTime, refetchInterval, retry, `enabled`
// gating, the query-vs-mutation choice, and the cache surgery in
// `dropDeletedFileFromCache` — is hand-written on purpose and is never
// generated.
export { qk };

export type Health = Awaited<ReturnType<typeof getHealth>>;

/**
 * Gate a query on something being open/visible. Deliberately the only option we
 * expose, so callers can't drift the caching policy per call site — the ⌘K
 * palette reuses `useFiles`' key (and therefore its cache) instead of fetching
 * its own private, smaller list.
 */
export interface QueryGate {
  enabled?: boolean;
}

export function useFiles(prefix = "", limit = 100, { enabled = true }: QueryGate = {}) {
  return useQuery<FileMetadata[], ApiError>({
    queryKey: qk.files(prefix, limit),
    queryFn: () => getFiles(prefix, limit),
    enabled,
  });
}

export function useFileStats({ enabled = true }: QueryGate = {}) {
  return useQuery({
    queryKey: qk.stats(),
    queryFn: getFileStats,
    enabled,
  });
}

export function useUploadActivity(days = 7) {
  return useQuery({
    queryKey: qk.uploadActivity(days),
    queryFn: () => getUploadActivity(days),
  });
}

// Content-proxy preview URL — only fetched when `enabled` is true (e.g., when
// the dialog opens for a specific file). Kept short-lived (60s): it is cheap to
// regenerate and a stale one could point at a key deleted meanwhile.
export function usePreviewUrl(key: string | undefined, enabled: boolean) {
  return useQuery({
    queryKey: qk.preview(key ?? ""),
    queryFn: () => getPreviewUrl(key as string),
    enabled: enabled && !!key,
    staleTime: 60_000,
  });
}

// Rich metadata for an already-stored file. The server recomputes it on demand
// (a full object download), so it's only fetched when `enabled` — i.e. the
// preview dialog is open AND the user expands "Detailed metadata". Kept
// short-lived like the preview URL; cheap correctness under key overwrites.
export function useFileDetail(key: string | undefined, enabled: boolean) {
  return useQuery<FileMetadataDetail, ApiError>({
    queryKey: qk.detail(key ?? ""),
    queryFn: () => getFileDetail(key as string),
    enabled: enabled && !!key,
    staleTime: 60_000,
  });
}

// Health poll for the top-of-app banner. `retry: false` and letting a failed
// fetch leave `data` undefined keeps a down API silent (the per-component
// ErrorState covers that); the banner only reacts to an up API reporting
// b2_connected: false or qdrant.ok: false. Polls every 60s and on focus.
export function useHealth() {
  return useQuery<Health>({
    queryKey: qk.health(),
    queryFn: getHealth,
    refetchInterval: 60_000,
    staleTime: 30_000,
    retry: false,
  });
}

/**
 * Drop a deleted object from every cached file list, plus its own cached
 * preview/detail entries.
 *
 * Invalidation alone is not enough: the refetch re-lists the whole bucket and
 * took 5-6s in practice, so the success toast fired while the row was still
 * listed — and using that stale row's Preview 404'd. Editing the cache makes
 * the row disappear with the toast; the invalidation that follows still
 * reconciles against the server.
 *
 * Exported for tests — the mutation below is its only production caller.
 */
export function dropDeletedFileFromCache(qc: QueryClient, fileKey: string) {
  qc.setQueriesData<FileMetadata[]>(
    // Partial key: matches qk.files(prefix, limit) for every prefix/limit.
    { queryKey: [...qk.all, "files"] },
    (previous) =>
      previous ? previous.filter((file) => file.key !== fileKey) : previous,
  );
  // A content URL for a deleted key can only 404 now.
  qc.removeQueries({ queryKey: qk.preview(fileKey) });
  qc.removeQueries({ queryKey: qk.detail(fileKey) });
}

/**
 * Fetch a download URL for one file.
 *
 * A mutation, not a query: it has a server side effect (it bumps the download
 * counter) and it must never be cached or replayed. Being a mutation is also
 * what gives the UI an honest pending state — the old code awaited the presign
 * inside a plain click handler, so a slow round trip left the screen completely
 * unchanged and a user could not tell a working download from a dead button.
 *
 * The caller performs the navigation (see `lib/browser-download.ts`) and gets
 * `isPending` / `variables` for the pending row.
 */
export function useDownloadUrl() {
  const qc = useQueryClient();
  return useMutation<FileUrlResponse, ApiError, FileMetadata>({
    mutationFn: (file) => getDownloadUrl(file.key),
    // The server counted a download, so the dashboard's "Total Downloads" is
    // now stale. Cheap: /files/stats reads a cached bucket listing.
    onSuccess: () => qc.invalidateQueries({ queryKey: qk.stats() }),
  });
}

export function useDeleteFile() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (fileKey: string) => deleteFile(fileKey),
    onSuccess: (_data, fileKey) => {
      // Remove the row immediately, then reconcile everything (lists, stats,
      // activity) against the server in the background.
      dropDeletedFileFromCache(qc, fileKey);
      qc.invalidateQueries({ queryKey: qk.all });
    },
  });
}

// --- tenants, tiering, reports, library --------------------------------------
//
// Tenant state changes underneath the UI (the background sweep parks idle
// tenants), so the tenant list and the tiering stats poll. Every mutation that
// can change a tenant's state invalidates the tenants subtree AND the tiering
// stats, which is what keeps the dashboard and the table in agreement.

const TENANT_POLL_MS = 15_000;

export function useTenants() {
  return useQuery({
    queryKey: qk.tenants(),
    queryFn: listTenants,
    refetchInterval: TENANT_POLL_MS,
  });
}

/** The generated key covers the detail subtree; the id is appended here. */
export const tenantKey = (tenantId: string) => [...qk.tenant(), tenantId] as const;
export const snapshotsKey = (tenantId: string) => [...qk.tenantSnapshots(), tenantId] as const;
export const reportKey = (runId: string) => [...qk.report(), runId] as const;

export function useTenant(tenantId: string) {
  return useQuery<TenantDetail, ApiError>({
    queryKey: tenantKey(tenantId),
    queryFn: () => getTenant(tenantId),
    refetchInterval: TENANT_POLL_MS,
    retry: (count, error) => !error.isNotFound && count < 2,
  });
}

export function useTenantSnapshots(tenantId: string) {
  return useQuery({
    queryKey: snapshotsKey(tenantId),
    queryFn: () => listTenantSnapshots(tenantId),
  });
}

export function useTieringStats() {
  return useQuery({
    queryKey: qk.tieringStats(),
    queryFn: getTieringStats,
    refetchInterval: TENANT_POLL_MS,
  });
}

export function useTieringPolicy() {
  return useQuery({
    queryKey: qk.tieringPolicy(),
    queryFn: getTieringPolicy,
    staleTime: 5 * 60_000,
  });
}

export function useReports() {
  return useQuery({ queryKey: qk.reports(), queryFn: listReports });
}

export function useReport(runId: string) {
  return useQuery<LatencyReport, ApiError>({
    queryKey: reportKey(runId),
    queryFn: () => getReport(runId),
    // A written report never changes.
    staleTime: Infinity,
    retry: (count, error) => !error.isNotFound && count < 2,
  });
}

export function useLibrary(tenantId?: string, kind?: string) {
  return useQuery({
    queryKey: qk.library(tenantId, kind),
    queryFn: () => listLibrary(tenantId, kind),
  });
}

/** Everything a tenant state change can make stale. */
export function invalidateTenantState(qc: QueryClient) {
  qc.invalidateQueries({ queryKey: qk.tenants() });
  qc.invalidateQueries({ queryKey: [...qk.all, "tiering"] });
  qc.invalidateQueries({ queryKey: [...qk.all, "library"] });
  // The bucket explorer lists the same objects.
  qc.invalidateQueries({ queryKey: [...qk.all, "files"] });
  qc.invalidateQueries({ queryKey: qk.stats() });
}

function useTenantMutation<TVars, TResult>(fn: (vars: TVars) => Promise<TResult>) {
  const qc = useQueryClient();
  return useMutation<TResult, ApiError, TVars>({
    mutationFn: fn,
    onSuccess: () => invalidateTenantState(qc),
  });
}

export const useCreateTenant = () =>
  useTenantMutation((body: TenantCreate) => createTenant(body));
export const useSeedTenants = () =>
  useTenantMutation((tenantCount: number) => seedTenants({ tenant_count: tenantCount }));
export const useUpdateTenant = (tenantId: string) =>
  useTenantMutation((body: TenantUpdate) => updateTenant(tenantId, body));
export const useDeleteTenant = (tenantId: string) =>
  useTenantMutation((confirm: string) => deleteTenant(tenantId, confirm));
export const useParkTenant = (tenantId: string) =>
  useTenantMutation(() => parkTenant(tenantId));
export const useRestoreTenant = (tenantId: string) =>
  useTenantMutation(() => restoreTenant(tenantId));
export const useRunTiering = () =>
  useTenantMutation((body: TieringRunRequest) => runTiering(body));
export const usePruneSnapshots = () =>
  useTenantMutation((body: PruneRequest) => pruneSnapshots(body));

/**
 * A query is a mutation here, not a cached read: it has side effects (it can
 * restore a parked tenant and it resets the idle clock) and every run is timed.
 */
export const useQueryTenant = (tenantId: string) =>
  useTenantMutation<QueryRequest, QueryResponse>((body) => queryTenant(tenantId, body));

export function useRunBenchmark() {
  const qc = useQueryClient();
  return useMutation<LatencyReport, ApiError, BenchmarkRequest>({
    mutationFn: runBenchmark,
    onSuccess: (report) => {
      qc.setQueryData(reportKey(report.run_id), report);
      qc.invalidateQueries({ queryKey: qk.reports() });
      invalidateTenantState(qc);
    },
  });
}
