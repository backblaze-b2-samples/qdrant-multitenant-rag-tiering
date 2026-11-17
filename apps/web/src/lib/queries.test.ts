import { MutationObserver, QueryClient, QueryObserver } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  dropDeletedFileFromCache,
  invalidateTenantState,
  markRestored,
  progressPollMs,
  progressQueryFn,
  qk,
  SEED_MUTATION_KEY,
  seedMutationOptions,
  tenantKey,
} from "@/lib/queries";
import type {
  FileMetadata,
  TenantDetail,
  TenantSummary,
} from "@qdrant-multitenant-rag-tiering/shared";

function file(key: string): FileMetadata {
  return {
    key,
    filename: key.split("/").pop() ?? key,
    folder: "uploads/",
    size_bytes: 10,
    size_human: "10 B",
    content_type: "text/plain",
    uploaded_at: "2026-07-28T00:00:00Z",
    url: null,
  };
}

describe("dropDeletedFileFromCache", () => {
  let qc: QueryClient;

  beforeEach(() => {
    qc = new QueryClient();
  });

  it("removes the deleted row from the default list", () => {
    qc.setQueryData(qk.files(), [file("uploads/a.txt"), file("uploads/b.txt")]);

    dropDeletedFileFromCache(qc, "uploads/a.txt");

    expect(qc.getQueryData<FileMetadata[]>(qk.files())).toEqual([
      file("uploads/b.txt"),
    ]);
  });

  it("removes it from every cached prefix/limit variant", () => {
    qc.setQueryData(qk.files(), [file("uploads/a.txt")]);
    qc.setQueryData(qk.files("uploads/", 100), [file("uploads/a.txt")]);
    qc.setQueryData(qk.files("", 25), [file("uploads/a.txt")]);

    dropDeletedFileFromCache(qc, "uploads/a.txt");

    expect(qc.getQueryData<FileMetadata[]>(qk.files())).toEqual([]);
    expect(qc.getQueryData<FileMetadata[]>(qk.files("uploads/", 100))).toEqual(
      [],
    );
    expect(qc.getQueryData<FileMetadata[]>(qk.files("", 25))).toEqual([]);
  });

  it("evicts the deleted key's preview URL and detail so Preview can't 404", () => {
    qc.setQueryData(qk.preview("uploads/a.txt"), { url: "https://signed" });
    qc.setQueryData(qk.detail("uploads/a.txt"), { md5: "abc" });

    dropDeletedFileFromCache(qc, "uploads/a.txt");

    expect(qc.getQueryData(qk.preview("uploads/a.txt"))).toBeUndefined();
    expect(qc.getQueryData(qk.detail("uploads/a.txt"))).toBeUndefined();
  });

  it("leaves other files' cached previews alone", () => {
    qc.setQueryData(qk.preview("uploads/b.txt"), { url: "https://signed-b" });

    dropDeletedFileFromCache(qc, "uploads/a.txt");

    expect(qc.getQueryData(qk.preview("uploads/b.txt"))).toEqual({
      url: "https://signed-b",
    });
  });

  it("does not touch stats or activity caches", () => {
    qc.setQueryData(qk.stats(), { total_files: 2 });
    qc.setQueryData(qk.uploadActivity(7), [{ date: "2026-07-28", uploads: 2 }]);

    dropDeletedFileFromCache(qc, "uploads/a.txt");

    expect(qc.getQueryData(qk.stats())).toEqual({ total_files: 2 });
    expect(qc.getQueryData(qk.uploadActivity(7))).toHaveLength(1);
  });

  it("is a no-op for an unseeded cache", () => {
    expect(() =>
      dropDeletedFileFromCache(qc, "uploads/missing.txt"),
    ).not.toThrow();
    expect(qc.getQueryData(qk.files())).toBeUndefined();
  });
});

describe("invalidateTenantState", () => {
  it("resolves only once the visible tenants list has refetched", async () => {
    const qc = new QueryClient();
    let calls = 0;
    const observer = new QueryObserver(qc, {
      queryKey: qk.tenants(),
      queryFn: async () => {
        calls += 1;
        await new Promise((resolve) => setTimeout(resolve, 20));
        return calls === 1 ? ["a", "b"] : ["a", "b", "c", "d"];
      },
    });
    const unsubscribe = observer.subscribe(() => {});
    await qc.fetchQuery({ queryKey: qk.tenants() });

    await invalidateTenantState(qc);

    // The success toast fires after this resolves, so the table must already
    // show every seeded tenant, not the pre-seed list.
    expect(qc.getQueryData(qk.tenants())).toEqual(["a", "b", "c", "d"]);
    unsubscribe();
  });
});

describe("markRestored", () => {
  it("flips a parked tenant to hot in the detail and list caches at once", () => {
    const qc = new QueryClient();
    const summary = { tenant_id: "t1", state: "parked" } as TenantSummary;
    qc.setQueryData(tenantKey("t1"), { ...summary } as TenantDetail);
    qc.setQueryData(qk.tenants(), [summary, { tenant_id: "t2", state: "parked" }]);

    markRestored(qc, "t1");

    expect(qc.getQueryData<TenantDetail>(tenantKey("t1"))?.state).toBe("hot");
    expect(qc.getQueryData<TenantSummary[]>(qk.tenants())?.map((t) => t.state)).toEqual([
      "hot",
      "parked",
    ]);
  });
});

describe("progressQueryFn", () => {
  const progress = (running: boolean) => ({
    running,
    phase: null,
    tenant_id: null,
    tenants_done: 0,
    tenants_total: 1,
    tenant_ids: ["a"],
    started_at: null,
    last_run_id: running ? null : "r2",
  });

  it("marks the reports list stale when a watched run finishes", async () => {
    const qc = new QueryClient();
    qc.setQueryData(qk.reportProgress(), progress(true));
    qc.setQueryData(qk.reports(), [{ run_id: "r1" }]);

    await progressQueryFn(qc, async () => progress(false))();

    expect(qc.getQueryState(qk.reports())?.isInvalidated).toBe(true);
    // Never its own key: that would cancel and restart this very fetch.
    expect(qc.getQueryState(qk.reportProgress())?.isInvalidated).toBe(false);
  });

  it("returns the idle progress only once the visible list shows the new report", async () => {
    // The "Benchmark finished" toast keys off the idle progress, so the list
    // beside it must already include the report (GET /reports takes seconds).
    const qc = new QueryClient();
    let calls = 0;
    const list = new QueryObserver(qc, {
      queryKey: qk.reports(),
      queryFn: async () => {
        calls += 1;
        await new Promise((resolve) => setTimeout(resolve, 20));
        return calls === 1 ? [{ run_id: "r1" }] : [{ run_id: "r2" }, { run_id: "r1" }];
      },
    });
    const unsubscribe = list.subscribe(() => {});
    await qc.fetchQuery({ queryKey: qk.reports() });
    qc.setQueryData(qk.reportProgress(), progress(true));

    await progressQueryFn(qc, async () => progress(false))();

    expect(qc.getQueryData(qk.reports())).toEqual([{ run_id: "r2" }, { run_id: "r1" }]);
    unsubscribe();
  });

  it("leaves the reports list alone while the run continues", async () => {
    const qc = new QueryClient();
    qc.setQueryData(qk.reportProgress(), progress(true));
    qc.setQueryData(qk.reports(), [{ run_id: "r1" }]);

    await progressQueryFn(qc, async () => progress(true))();

    expect(qc.getQueryState(qk.reports())?.isInvalidated).toBe(false);
  });
});

describe("seedMutationOptions", () => {
  it("stays visible and reports its result after the clicked control unmounts", async () => {
    // The table's empty state has its own Seed button; it unmounts as soon as
    // the first seeded tenant appears, which used to end "Seeding…" early.
    const qc = new QueryClient();
    let finish: (value: { created: string[]; skipped: string[] }) => void = () => {};
    const onSuccess = vi.fn();
    const observer = new MutationObserver(
      qc,
      seedMutationOptions(qc, { onSuccess }, () => new Promise((resolve) => (finish = resolve)))
    );
    const unsubscribe = observer.subscribe(() => {});
    const running = observer.mutate(4);
    unsubscribe();

    expect(qc.isMutating({ mutationKey: SEED_MUTATION_KEY })).toBe(1);

    await new Promise((resolve) => setTimeout(resolve, 0)); // let the request start
    finish({ created: ["a", "b", "c", "d"], skipped: [] });
    await running;

    expect(onSuccess).toHaveBeenCalledWith({ created: ["a", "b", "c", "d"], skipped: [] });
    expect(qc.isMutating({ mutationKey: SEED_MUTATION_KEY })).toBe(0);
  });
});

describe("progressPollMs", () => {
  it("polls every second while a run is live or starting here", () => {
    expect(progressPollMs(false, { running: true })).toBe(1_000);
    expect(progressPollMs(true, undefined)).toBe(1_000);
  });

  it("keeps a slow poll when idle, so a run started elsewhere is noticed", () => {
    expect(progressPollMs(false, { running: false })).toBe(10_000);
    expect(progressPollMs(false, undefined)).toBe(10_000);
  });
});
