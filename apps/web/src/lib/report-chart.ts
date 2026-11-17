import type { LatencyReport } from "@qdrant-multitenant-rag-tiering/shared";

/** One bar group per tenant: the three numbers the report is read for. */
export interface LatencyRow {
  tenant: string;
  warmP50: number;
  restoreTotal: number;
  postRestoreP50: number;
}

export interface MemoryRow {
  tenant: string;
  /** MiB, rounded to two decimals, so the axis stays readable. */
  estimateMiB: number;
  observedMiB: number | null;
}

const MIB = 1024 * 1024;

export function latencyRows(report: LatencyReport): LatencyRow[] {
  return report.tenants.map((t) => ({
    tenant: t.tenant_id,
    warmP50: t.warm.p50_ms,
    restoreTotal: t.restore.total_ms,
    postRestoreP50: t.post_restore.p50_ms,
  }));
}

export function memoryRows(report: LatencyReport): MemoryRow[] {
  const toMiB = (bytes: number) => Math.round((bytes / MIB) * 100) / 100;
  return report.tenants.map((t) => ({
    tenant: t.tenant_id,
    estimateMiB: toMiB(t.memory_freed.vector_bytes_estimate),
    observedMiB:
      t.memory_freed.node_rss_delta_bytes === null
        ? null
        : toMiB(Math.max(0, t.memory_freed.node_rss_delta_bytes)),
  }));
}

/** How many times slower the first query after a park is than a warm query. */
export function restorePenalty(report: LatencyReport): number | null {
  const ratios = report.tenants
    .filter((t) => t.warm.p50_ms > 0)
    .map((t) => t.first_query_after_restore_ms / t.warm.p50_ms);
  if (ratios.length === 0) return null;
  return Math.round((ratios.reduce((a, b) => a + b, 0) / ratios.length) * 10) / 10;
}

export function allResultsMatch(report: LatencyReport): boolean {
  return report.tenants.every((t) => t.results_match);
}
