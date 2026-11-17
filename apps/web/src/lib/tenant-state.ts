import type {
  BenchmarkProgress,
  TenantProgress,
  TenantSummary,
} from "@qdrant-multitenant-rag-tiering/shared";

import { humanizeBytes } from "@/lib/utils";

export type TenantState = TenantSummary["state"];

export interface StateBadge {
  label: string;
  /** Plain-language meaning, used as the badge tooltip. */
  description: string;
  /** Token-based classes; never a raw palette colour. */
  className: string;
  /** True while a park or restore is running for this tenant. */
  busy: boolean;
}

const BADGES: Record<TenantState, StateBadge> = {
  hot: {
    label: "Hot",
    description: "Collection loaded in Qdrant; queries answer immediately.",
    className: "border-transparent bg-success-subtle text-success",
    busy: false,
  },
  parked: {
    label: "Parked in B2",
    description: "Verified snapshot in B2; the next query restores it.",
    className: "border-border bg-muted text-foreground",
    busy: false,
  },
  empty: {
    label: "Empty",
    description: "No indexed documents yet; add documents to make it hot.",
    className: "border-dashed border-border bg-transparent text-muted-foreground",
    busy: false,
  },
  writing: {
    label: "Writing",
    description: "Writing the documents to B2.",
    className: "border-transparent bg-attention-subtle text-attention",
    busy: true,
  },
  embedding: {
    label: "Embedding",
    description: "Chunking and embedding the documents.",
    className: "border-transparent bg-attention-subtle text-attention",
    busy: true,
  },
  upserting: {
    label: "Indexing",
    description: "Upserting the vectors into the tenant's Qdrant collection.",
    className: "border-transparent bg-attention-subtle text-attention",
    busy: true,
  },
  snapshotting: {
    label: "Snapshotting",
    description: "Qdrant is writing a snapshot of the collection.",
    className: "border-transparent bg-attention-subtle text-attention",
    busy: true,
  },
  uploading: {
    label: "Uploading",
    description: "Streaming the snapshot from Qdrant to B2.",
    className: "border-transparent bg-attention-subtle text-attention",
    busy: true,
  },
  verifying: {
    label: "Verifying",
    description: "Re-reading the snapshot from B2 to check size and sha256.",
    className: "border-transparent bg-attention-subtle text-attention",
    busy: true,
  },
  dropping: {
    label: "Dropping",
    description: "Snapshot verified; dropping the collection from Qdrant.",
    className: "border-transparent bg-attention-subtle text-attention",
    busy: true,
  },
  restoring: {
    label: "Restoring",
    description: "Loading the snapshot from B2 into Qdrant.",
    className: "border-transparent bg-attention-subtle text-attention",
    busy: true,
  },
};

export function stateBadge(state: TenantState): StateBadge {
  return BADGES[state];
}

/** The park state machine's stages, in the order the API reports them. */
const PARK_STAGES: TenantState[] = ["snapshotting", "uploading", "verifying", "dropping"];

/** "Step n of 4: <what is happening>" while a park runs, else null. */
export function parkStageText(state: TenantState): string | null {
  const index = PARK_STAGES.indexOf(state);
  if (index < 0) return null;
  return `Step ${index + 1} of ${PARK_STAGES.length}: ${BADGES[state].description}`;
}

/** The create stages, in the order the API reports them. */
const CREATE_STAGES: TenantState[] = ["writing", "embedding", "upserting"];

/**
 * The create dialog's line and determinate bar, from GET /tenants/<id>/progress.
 * Before the server reports a stage it is step 1 (the request is on its way);
 * once a stage was seen (`started`), an idle reply means indexing is done.
 */
export function createProgress(
  progress: Pick<TenantProgress, "state" | "done" | "total"> | undefined,
  started: boolean
): { text: string; percent: number } | null {
  const state = progress?.state ?? (started ? null : "writing");
  const index = state ? CREATE_STAGES.indexOf(state) : -1;
  if (index < 0) return null;
  const { done, total } = progress?.state ? progress : { done: null, total: null };
  let count = "";
  if (done !== null && total) {
    if (state === "writing") count = ` (document ${Math.min(done + 1, total)} of ${total})`;
    if (state === "embedding") count = ` (${done} of ${total} chunks)`;
  }
  const fraction = done !== null && total ? done / total : 0;
  return {
    text: `Step ${index + 1} of ${CREATE_STAGES.length}: ${BADGES[state as TenantState].description.replace(/\.$/, "")}${count}`,
    percent: Math.round(((index + fraction) / CREATE_STAGES.length) * 100),
  };
}

/** States in which the collection is (still) loaded in Qdrant. */
const LOADED: TenantState[] = ["hot", ...PARK_STAGES];

/**
 * Vector memory in Qdrant now, the same text on the table and the detail page.
 * A parked tenant uses 0 B; the estimate it freed is shown alongside.
 */
export function vectorMemoryText(
  tenant: Pick<TenantSummary, "state" | "vector_bytes_estimate">
): string {
  if (LOADED.includes(tenant.state)) return humanizeBytes(tenant.vector_bytes_estimate);
  if (tenant.state === "parked" && tenant.vector_bytes_estimate > 0) {
    return `0 B (${humanizeBytes(tenant.vector_bytes_estimate)} freed)`;
  }
  return "0 B";
}

export interface SweepProgress {
  active: { tenant_id: string; stage: string | null }[];
  /** Tenants hot when the sweep began that are parked now. */
  done: number;
  /** Known only when a dry run listed the candidates first. */
  total: number | null;
}

/** What a running sweep is doing, read from the polled tenant list. */
export function sweepProgress(
  hotAtStart: string[],
  tenants: TenantSummary[],
  candidates: string[] | null
): SweepProgress {
  return {
    active: tenants
      .filter((t) => PARK_STAGES.includes(t.state))
      .map((t) => ({ tenant_id: t.tenant_id, stage: parkStageText(t.state) })),
    done: tenants.filter((t) => hotAtStart.includes(t.tenant_id) && t.state === "parked").length,
    total: candidates ? candidates.length : null,
  };
}

/**
 * Benchmark checklist rows: hot and parked tenants can be picked; tenants in a
 * transitional state (e.g. the one a running benchmark is parking) stay listed
 * but disabled, so they never vanish mid-run.
 */
export function benchmarkChoices(tenants: TenantSummary[]) {
  return tenants
    .filter((t) => t.state !== "empty")
    .map((t) => ({ tenant: t, selectable: t.state === "hot" || t.state === "parked" }));
}

const BENCHMARK_PHASES: Record<NonNullable<BenchmarkProgress["phase"]>, string> = {
  warm: "warm queries",
  park: "parking to B2",
  restore: "restoring from B2 on the first query",
  post_restore: "post-restore queries",
};

/** The checklist's ticks: a running run's own tenants (even after a reload), else the page's selection. */
export function checkedForBenchmark(
  selected: string[],
  progress: BenchmarkProgress | undefined
): string[] {
  return progress?.running && progress.tenant_ids.length ? progress.tenant_ids : selected;
}

/** "Tenant n of N (id): phase" for a running benchmark, else null. */
export function benchmarkProgressText(progress: BenchmarkProgress | undefined): string | null {
  if (!progress?.running) return null;
  const position = `Tenant ${Math.min(progress.tenants_done + 1, progress.tenants_total)} of ${progress.tenants_total}`;
  if (!progress.phase || !progress.tenant_id) return `${position}: starting`;
  return `${position} (${progress.tenant_id}): ${BENCHMARK_PHASES[progress.phase]}`;
}

/**
 * The report id when a watched benchmark went from running to idle: "" if it
 * ended without a report (it failed), null when nothing just finished.
 */
export function finishedRunId(
  previous: BenchmarkProgress | undefined,
  next: BenchmarkProgress | undefined
): string | null {
  if (!previous?.running || !next || next.running) return null;
  return next.last_run_id ?? "";
}

/** Ids of hot tenants, in table order: the default benchmark selection. */
export function defaultBenchmarkSelection(tenants: TenantSummary[]): string[] {
  const firstHot = tenants.find((t) => t.state === "hot");
  return firstHot ? [firstHot.tenant_id] : [];
}

export function formatMs(ms: number): string {
  if (ms < 1) return `${ms.toFixed(2)} ms`;
  if (ms < 1000) return `${ms.toFixed(ms < 10 ? 1 : 0)} ms`;
  return `${(ms / 1000).toFixed(2)} s`;
}

export function formatAge(iso: string | null, now: number = Date.now()): string {
  if (!iso) return "never";
  const seconds = Math.max(0, Math.round((now - new Date(iso).getTime()) / 1000));
  if (seconds < 60) return `${seconds}s ago`;
  if (seconds < 3600) return `${Math.round(seconds / 60)} min ago`;
  if (seconds < 86_400) return `${Math.round(seconds / 3600)} h ago`;
  return `${Math.round(seconds / 86_400)} d ago`;
}
