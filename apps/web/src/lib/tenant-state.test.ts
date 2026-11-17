import { describe, expect, it } from "vitest";

import type { TenantSummary } from "@qdrant-multitenant-rag-tiering/shared";

import {
  defaultBenchmarkSelection,
  formatAge,
  formatMs,
  stateBadge,
  type TenantState,
} from "./tenant-state";

const ALL: TenantState[] = ["hot", "parked", "empty", "snapshotting", "verifying", "restoring"];

function tenant(id: string, state: TenantState): TenantSummary {
  return {
    tenant_id: id,
    display_name: id,
    state,
    point_count: 0,
    document_count: 0,
    vector_bytes_estimate: 0,
    last_query_at: null,
    snapshot_size_bytes: null,
    snapshot_created_at: null,
  };
}

describe("stateBadge", () => {
  it("has a label and description for every state", () => {
    for (const state of ALL) {
      const badge = stateBadge(state);
      expect(badge.label).not.toBe("");
      expect(badge.description).not.toBe("");
    }
  });

  it("marks only the transitional states as busy", () => {
    expect(ALL.filter((s) => stateBadge(s).busy)).toEqual([
      "snapshotting",
      "verifying",
      "restoring",
    ]);
  });

  it("uses design tokens, never raw palette colours", () => {
    for (const state of ALL) {
      expect(stateBadge(state).className).not.toMatch(/(green|red|yellow|amber)-\d/);
    }
  });
});

describe("defaultBenchmarkSelection", () => {
  it("picks the first hot tenant", () => {
    expect(
      defaultBenchmarkSelection([tenant("a", "parked"), tenant("b", "hot"), tenant("c", "hot")])
    ).toEqual(["b"]);
  });

  it("is empty when nothing is hot", () => {
    expect(defaultBenchmarkSelection([tenant("a", "parked")])).toEqual([]);
  });
});

describe("formatting", () => {
  it("formats latencies across scales", () => {
    expect(formatMs(0.5)).toBe("0.50 ms");
    expect(formatMs(4.25)).toBe("4.3 ms");
    expect(formatMs(250)).toBe("250 ms");
    expect(formatMs(1500)).toBe("1.50 s");
  });

  it("formats idle ages", () => {
    const now = Date.parse("2026-11-17T12:00:00Z");
    expect(formatAge(null, now)).toBe("never");
    expect(formatAge("2026-11-17T11:59:30Z", now)).toBe("30s ago");
    expect(formatAge("2026-11-17T11:00:00Z", now)).toBe("1 h ago");
  });
});
