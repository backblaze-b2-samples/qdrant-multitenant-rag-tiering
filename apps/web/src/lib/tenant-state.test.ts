import { describe, expect, it } from "vitest";

import type { TenantSummary } from "@qdrant-multitenant-rag-tiering/shared";

import {
  benchmarkChoices,
  checkedForBenchmark,
  benchmarkProgressText,
  createProgress,
  defaultBenchmarkSelection,
  finishedRunId,
  formatAge,
  formatMs,
  parkStageText,
  stateBadge,
  sweepProgress,
  vectorMemoryText,
  type TenantState,
} from "./tenant-state";

const ALL: TenantState[] = [
  "hot",
  "parked",
  "empty",
  "writing",
  "embedding",
  "upserting",
  "snapshotting",
  "uploading",
  "verifying",
  "dropping",
  "restoring",
];

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
      "writing",
      "embedding",
      "upserting",
      "snapshotting",
      "uploading",
      "verifying",
      "dropping",
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

describe("parkStageText", () => {
  it("numbers the four park stages in order", () => {
    expect(parkStageText("snapshotting")).toMatch(/^Step 1 of 4: /);
    expect(parkStageText("uploading")).toMatch(/^Step 2 of 4: /);
    expect(parkStageText("verifying")).toMatch(/^Step 3 of 4: /);
    expect(parkStageText("dropping")).toMatch(/^Step 4 of 4: /);
  });

  it("is null outside a park", () => {
    expect(parkStageText("hot")).toBeNull();
    expect(parkStageText("parked")).toBeNull();
    expect(parkStageText("restoring")).toBeNull();
  });
});

describe("vectorMemoryText", () => {
  const sized = (state: TenantState) => ({ ...tenant("t", state), vector_bytes_estimate: 2048 });

  it("shows the in-Qdrant footprint while the collection is loaded", () => {
    expect(vectorMemoryText(sized("hot"))).toBe("2.0 KB");
    expect(vectorMemoryText(sized("verifying"))).toBe("2.0 KB");
  });

  it("shows 0 B in Qdrant plus what parking freed, the same on every surface", () => {
    expect(vectorMemoryText(sized("parked"))).toBe("0 B (2.0 KB freed)");
  });

  it("is 0 B for an empty tenant", () => {
    expect(vectorMemoryText(tenant("t", "empty"))).toBe("0 B");
  });
});

describe("sweepProgress", () => {
  it("lists tenants mid-park and counts the ones parked since the sweep began", () => {
    const now = [tenant("a", "parked"), tenant("b", "uploading"), tenant("c", "hot")];
    expect(sweepProgress(["a", "b", "c"], now, ["a", "b"])).toEqual({
      active: [{ tenant_id: "b", stage: parkStageText("uploading") }],
      done: 1,
      total: 2,
    });
  });

  it("has no total when the candidates are not known yet", () => {
    expect(sweepProgress(["a"], [tenant("a", "snapshotting")], null).total).toBeNull();
  });
});

describe("benchmarkChoices", () => {
  it("keeps transitional tenants visible but not selectable", () => {
    const choices = benchmarkChoices([
      tenant("a", "hot"),
      tenant("b", "verifying"),
      tenant("c", "empty"),
      tenant("d", "parked"),
    ]);
    expect(choices.map((c) => [c.tenant.tenant_id, c.selectable])).toEqual([
      ["a", true],
      ["b", false],
      ["d", true],
    ]);
  });
});

describe("benchmarkProgressText", () => {
  const progress = {
    running: true,
    phase: "park" as const,
    tenant_id: "acme-legal",
    tenants_done: 1,
    tenants_total: 3,
    tenant_ids: ["x", "acme-legal", "y"],
    started_at: "2026-11-17T12:00:00Z",
    last_run_id: null,
  };

  it("names the tenant n of N and the phase", () => {
    expect(benchmarkProgressText(progress)).toBe(
      "Tenant 2 of 3 (acme-legal): parking to B2"
    );
  });

  it("is null when nothing is running", () => {
    expect(benchmarkProgressText({ ...progress, running: false })).toBeNull();
    expect(benchmarkProgressText(undefined)).toBeNull();
  });
});

describe("createProgress", () => {
  const at = (state: TenantState | null, done: number | null = null, total: number | null = null) => ({
    tenant_id: "t",
    state,
    done,
    total,
  });

  it("numbers the three create stages in order", () => {
    expect(createProgress(at("writing", 0, 3), false)?.text).toMatch(/^Step 1 of 3: /);
    expect(createProgress(at("embedding", 0, 10), true)?.text).toMatch(/^Step 2 of 3: /);
    expect(createProgress(at("upserting", 0, 1), true)?.text).toMatch(/^Step 3 of 3: /);
  });

  it("counts documents while writing and chunks while embedding", () => {
    expect(createProgress(at("writing", 1, 3), false)?.text).toBe(
      "Step 1 of 3: Writing the documents to B2 (document 2 of 3)"
    );
    expect(createProgress(at("embedding", 40, 120), true)?.text).toBe(
      "Step 2 of 3: Chunking and embedding the documents (40 of 120 chunks)"
    );
  });

  it("gives a determinate overall percentage that only moves forward", () => {
    const percents = [
      createProgress(at("writing", 0, 3), false)?.percent,
      createProgress(at("writing", 2, 3), true)?.percent,
      createProgress(at("embedding", 60, 120), true)?.percent,
      createProgress(at("upserting", 0, 1), true)?.percent,
    ];
    expect(percents).toEqual([0, 22, 50, 67]);
  });

  it("is step 1 before the server reports a stage, and null once it is done", () => {
    expect(createProgress(at(null), false)?.text).toMatch(/^Step 1 of 3: Writing/);
    expect(createProgress(undefined, false)?.text).toMatch(/^Step 1 of 3: Writing/);
    expect(createProgress(at(null), true)).toBeNull();
  });
});

describe("finishedRunId", () => {
  const running = {
    running: true,
    phase: "warm" as const,
    tenant_id: "a",
    tenants_done: 0,
    tenants_total: 1,
    tenant_ids: ["a"],
    started_at: null,
    last_run_id: null,
  };

  it("returns the new report when a watched run goes idle", () => {
    expect(finishedRunId(running, { ...running, running: false, last_run_id: "r2" })).toBe("r2");
  });

  it("returns null without a running-to-idle transition", () => {
    const idle = { ...running, running: false, last_run_id: "r1" };
    expect(finishedRunId(idle, idle)).toBeNull();
    expect(finishedRunId(undefined, idle)).toBeNull();
    expect(finishedRunId(running, running)).toBeNull();
  });

  it("returns an empty string when the run ended without a report (it failed)", () => {
    expect(finishedRunId(running, { ...running, running: false })).toBe("");
  });
});

describe("checkedForBenchmark", () => {
  const run = {
    running: true,
    phase: "warm" as const,
    tenant_id: "oss-readmes",
    tenants_done: 1,
    tenants_total: 2,
    tenant_ids: ["acme-legal", "oss-readmes"],
    started_at: null,
    last_run_id: null,
  };

  it("shows the running run's tenants, not this page's default selection", () => {
    expect(checkedForBenchmark(["acme-legal"], run)).toEqual(["acme-legal", "oss-readmes"]);
  });

  it("shows the page's own selection when nothing runs", () => {
    expect(checkedForBenchmark(["acme-legal"], { ...run, running: false })).toEqual(["acme-legal"]);
    expect(checkedForBenchmark(["acme-legal"], undefined)).toEqual(["acme-legal"]);
  });
});
