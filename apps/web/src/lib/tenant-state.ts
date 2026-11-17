import type { TenantSummary } from "@qdrant-multitenant-rag-tiering/shared";

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
  snapshotting: {
    label: "Snapshotting",
    description: "Streaming a snapshot from Qdrant to B2.",
    className: "border-transparent bg-attention-subtle text-attention",
    busy: true,
  },
  verifying: {
    label: "Verifying",
    description: "Re-reading the snapshot from B2 to check size and sha256.",
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
