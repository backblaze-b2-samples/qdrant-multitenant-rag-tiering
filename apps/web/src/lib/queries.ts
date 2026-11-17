"use client";

import {
  useIsMutating,
  useMutation,
  useQuery,
  useQueryClient,
  type MutationOptions,
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
  getBenchmarkProgress,
  getFileStats,
  getHealth,
  getPreviewUrl,
  getReport,
  getTenant,
  getTenantProgress,
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
  BenchmarkProgress,
  BenchmarkRequest,
  FileMetadata,
  FileMetadataDetail,
  FileUrlResponse,
  LatencyReport,
  PruneRequest,
  QueryRequest,
  QueryResponse,
  SeedResult,
  TenantCreate,
  TenantDetail,
  TenantSummary,
  TenantUpdate,
  TieringRunRequest,
} from "@qdrant-multitenant-rag-tiering/shared";
import { qk } from "@/lib/generated/query-keys";
import { stateBadge } from "@/lib/tenant-state";

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
/** While a park, sweep, restore or benchmark runs, poll fast enough to show each stage. */
const BUSY_POLL_MS = 1_000;
const IDLE_PROGRESS_POLL_MS = 10_000;

/** Options for the tenant reads. `busy`: an operation on this page is running. */
export interface TenantPoll {
  busy?: boolean;
}

const pollEvery = (busy: boolean) => (busy ? BUSY_POLL_MS : TENANT_POLL_MS);

export function useTenants({ busy = false }: TenantPoll = {}) {
  return useQuery({
    queryKey: qk.tenants(),
    queryFn: listTenants,
    refetchInterval: (query) =>
      pollEvery(busy || !!query.state.data?.some((t) => stateBadge(t.state).busy)),
  });
}

/** The generated key covers the detail subtree; the id is appended here. */
export const tenantKey = (tenantId: string) => [...qk.tenant(), tenantId] as const;
export const snapshotsKey = (tenantId: string) => [...qk.tenantSnapshots(), tenantId] as const;
export const reportKey = (runId: string) => [...qk.report(), runId] as const;

export function useTenant(tenantId: string, { busy = false }: TenantPoll = {}) {
  return useQuery<TenantDetail, ApiError>({
    queryKey: tenantKey(tenantId),
    queryFn: () => getTenant(tenantId),
    refetchInterval: (query) =>
      pollEvery(busy || (!!query.state.data && stateBadge(query.state.data.state).busy)),
    retry: (count, error) => !error.isNotFound && count < 2,
  });
}

export const tenantProgressKey = (tenantId: string) =>
  [...qk.tenantProgress(), tenantId] as const;

/**
 * The stage and count running on one tenant (in memory on the API, no B2
 * read), polled every half second while `enabled`: the create dialog's
 * progress line. Answers even before the tenant's metadata exists.
 */
export function useTenantProgress(tenantId: string, { enabled = true }: QueryGate = {}) {
  return useQuery({
    queryKey: tenantProgressKey(tenantId),
    queryFn: () => getTenantProgress(tenantId),
    enabled: enabled && !!tenantId,
    staleTime: 0,
    refetchInterval: enabled ? 500 : false,
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

/**
 * Fetch the benchmark progress and, when a run this tab watched has just
 * finished, refetch the reports list so the new report appears. That covers
 * a tab reloaded mid-run, which has no mutation `onSuccess` of its own. Only the
 * list key is invalidated (`exact`): invalidating the progress key would cancel
 * and restart this very fetch.
 */
export function progressQueryFn(qc: QueryClient, fetchProgress: () => Promise<BenchmarkProgress>) {
  return async () => {
    const previous = qc.getQueryData<BenchmarkProgress>(qk.reportProgress());
    const next = await fetchProgress();
    if (previous?.running && !next.running) {
      // Awaited, so "finished" (and its toast) only shows once the list beside
      // it includes the new report; GET /reports reads every report.json.
      await qc.invalidateQueries({ queryKey: qk.reports(), exact: true });
    }
    return next;
  };
}

/**
 * Every second while a run is live; every 10 s when idle (an in-memory read on
 * the API), so a run started from another tab or a script still shows up.
 */
export function progressPollMs(busy: boolean, data: Pick<BenchmarkProgress, "running"> | undefined) {
  return busy || data?.running ? BUSY_POLL_MS : IDLE_PROGRESS_POLL_MS;
}

/**
 * The benchmark running on the API, if any. Read on mount so a reloaded
 * Reports page still shows a run in flight; polled every second while one runs.
 */
export function useBenchmarkProgress({ busy = false }: TenantPoll = {}) {
  const qc = useQueryClient();
  return useQuery({
    queryKey: qk.reportProgress(),
    queryFn: progressQueryFn(qc, getBenchmarkProgress),
    staleTime: 0,
    refetchInterval: (query) => progressPollMs(busy, query.state.data),
  });
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

/**
 * Everything a tenant state change can make stale.
 *
 * Resolves once the tenant reads and tiering stats on screen have refetched,
 * and the tenant mutations return it from `onSuccess`, so a mutation (and its
 * success toast or result) only settles once the table already shows the new
 * state. Not awaiting it left the table on the pre-seed / pre-sweep rows for
 * seconds after "Seeded 4 tenant(s)". The library and bucket listings are
 * reconciled in the background: the bucket scan can take far longer.
 */
export function invalidateTenantState(qc: QueryClient): Promise<unknown> {
  qc.invalidateQueries({ queryKey: [...qk.all, "library"] });
  // The bucket explorer lists the same objects.
  qc.invalidateQueries({ queryKey: [...qk.all, "files"] });
  qc.invalidateQueries({ queryKey: qk.stats() });
  return Promise.all([
    qc.invalidateQueries({ queryKey: qk.tenants() }),
    qc.invalidateQueries({ queryKey: [...qk.all, "tiering"] }),
  ]);
}

/**
 * A query that restored a parked tenant made it hot: say so at once in the
 * cached detail and list, instead of showing "Parked in B2" beside the
 * restored answer until the refetch lands.
 */
export function markRestored(qc: QueryClient, tenantId: string) {
  qc.setQueryData<TenantDetail>(tenantKey(tenantId), (previous) =>
    previous ? { ...previous, state: "hot" } : previous
  );
  qc.setQueryData<TenantSummary[]>(qk.tenants(), (previous) =>
    previous?.map((t) => (t.tenant_id === tenantId ? { ...t, state: "hot" } : t))
  );
}

/** Options shared by every tenant mutation: settle only once the table is fresh. */
function tenantMutationOptions<TVars, TResult>(
  qc: QueryClient,
  fn: (vars: TVars) => Promise<TResult>,
  beforeRefetch?: (qc: QueryClient, result: TResult) => void
): MutationOptions<TResult, ApiError, TVars> {
  return {
    mutationFn: fn,
    onSuccess: (result) => {
      beforeRefetch?.(qc, result);
      return invalidateTenantState(qc);
    },
  };
}

function useTenantMutation<TVars, TResult>(
  fn: (vars: TVars) => Promise<TResult>,
  beforeRefetch?: (qc: QueryClient, result: TResult) => void
) {
  const qc = useQueryClient();
  return useMutation(tenantMutationOptions(qc, fn, beforeRefetch));
}

/** Identifies a running seed to every Seed control, wherever it was clicked. */
export const SEED_MUTATION_KEY = [...qk.tenants(), "seed"] as const;

export interface SeedCallbacks {
  onSuccess?: (result: SeedResult) => void;
  onError?: (error: ApiError) => void;
}

/**
 * The seed mutation. Its callbacks live on the mutation itself, not on one
 * `mutate` call, so the result toast still fires when the clicked control
 * unmounts (the table's empty-state button does, as soon as the first seeded
 * tenant is listed). `SEED_MUTATION_KEY` lets the other control show it running.
 * `run` is injectable for tests.
 */
export function seedMutationOptions(
  qc: QueryClient,
  { onSuccess, onError }: SeedCallbacks,
  run: (tenantCount: number) => Promise<SeedResult> = (n) => seedTenants({ tenant_count: n })
): MutationOptions<SeedResult, ApiError, number> {
  const base = tenantMutationOptions<number, SeedResult>(qc, run);
  return {
    ...base,
    mutationKey: SEED_MUTATION_KEY,
    onSuccess: async (result, ...rest) => {
      await base.onSuccess?.(result, ...rest);
      onSuccess?.(result);
    },
    onError: (error) => onError?.(error),
  };
}

export const useCreateTenant = () =>
  useTenantMutation((body: TenantCreate) => createTenant(body));
export function useSeedTenants(callbacks: SeedCallbacks = {}) {
  const qc = useQueryClient();
  const seed = useMutation(seedMutationOptions(qc, callbacks));
  // True while ANY Seed control's seed runs, not only this one's.
  const running = useIsMutating({ mutationKey: SEED_MUTATION_KEY }) > 0;
  return { seed, running };
}
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
  useTenantMutation<QueryRequest, QueryResponse>(
    (body) => queryTenant(tenantId, body),
    (qc, response) => {
      if (response.restored) markRestored(qc, tenantId);
    }
  );

export function useRunBenchmark() {
  const qc = useQueryClient();
  return useMutation<LatencyReport, ApiError, BenchmarkRequest>({
    mutationFn: runBenchmark,
    onSuccess: (report) => {
      qc.setQueryData(reportKey(report.run_id), report);
      qc.invalidateQueries({ queryKey: qk.reports() });
      void invalidateTenantState(qc);
    },
  });
}
