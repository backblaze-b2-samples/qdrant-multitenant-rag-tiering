import { describe, expect, it } from "vitest";

import type { LatencyReport, TenantLatency } from "@qdrant-multitenant-rag-tiering/shared";

import {
  allResultsMatch,
  latencyRows,
  memoryFreedCells,
  memoryRows,
  restorePenalty,
} from "./report-chart";

function stats(p50: number) {
  return { n: 10, p50_ms: p50, p95_ms: p50 * 2, mean_ms: p50 };
}

function entry(id: string, overrides: Partial<TenantLatency> = {}): TenantLatency {
  return {
    tenant_id: id,
    point_count: 12,
    warm: stats(4),
    snapshot_bytes: 2048,
    snapshot_upload_ms: 300,
    restore: { download_ms: 120, load_ms: 80, total_ms: 200 },
    first_query_after_restore_ms: 210,
    post_restore: stats(5),
    memory_freed: { vector_bytes_estimate: 3 * 1024 * 1024, node_rss_delta_bytes: -1024 },
    results_match: true,
    ...overrides,
  };
}

function report(tenants: TenantLatency[]): LatencyReport {
  return {
    run_id: "r1",
    created_at: "2026-11-17T12:00:00Z",
    qdrant_version: "1.20.2",
    embedding_model: "BAAI/bge-small-en-v1.5",
    tenants,
  };
}

describe("report chart shaping", () => {
  it("maps each tenant to warm, restore and post-restore figures", () => {
    expect(latencyRows(report([entry("a")]))).toEqual([
      { tenant: "a", warmP50: 4, restoreTotal: 200, postRestoreP50: 5 },
    ]);
  });

  it("converts memory to MiB and clamps a negative observed delta to zero", () => {
    expect(memoryRows(report([entry("a")]))).toEqual([
      { tenant: "a", estimateMiB: 3, observedMiB: 0 },
    ]);
  });

  it("keeps a missing observed metric as null rather than zero", () => {
    const r = report([
      entry("a", { memory_freed: { vector_bytes_estimate: 0, node_rss_delta_bytes: null } }),
    ]);
    expect(memoryRows(r)[0].observedMiB).toBeNull();
  });

  it("averages the restore penalty over tenants with a warm figure", () => {
    expect(restorePenalty(report([entry("a"), entry("b", { first_query_after_restore_ms: 410 })]))).toBe(
      77.5 // (210 / 4 + 410 / 4) / 2
    );
    expect(restorePenalty(report([]))).toBeNull();
  });

  it("flags any tenant whose results changed", () => {
    expect(allResultsMatch(report([entry("a"), entry("b", { results_match: false })]))).toBe(false);
  });
});

describe("memoryFreedCells", () => {
  it("gives readable estimate and observed RSS figures for the Figures table", () => {
    expect(
      memoryFreedCells(
        entry("a", {
          memory_freed: { vector_bytes_estimate: 377_446, node_rss_delta_bytes: 2 * 1024 * 1024 },
        })
      )
    ).toEqual({ estimate: "368.6 KB", observed: "2.0 MB" });
  });

  it("shows an observed drop of 0 B (not a blank) when RSS did not fall", () => {
    expect(memoryFreedCells(entry("a")).observed).toBe("0 B");
  });

  it("says the metric was unavailable when RSS is null", () => {
    const cells = memoryFreedCells(
      entry("a", { memory_freed: { vector_bytes_estimate: 0, node_rss_delta_bytes: null } })
    );
    expect(cells.observed).toBe("n/a");
  });
});
