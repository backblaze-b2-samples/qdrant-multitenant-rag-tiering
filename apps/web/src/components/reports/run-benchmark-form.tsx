"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { Gauge, Loader2 } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { StateBadge } from "@/components/tenants/state-badge";
import { useBenchmarkProgress, useRunBenchmark, useTenants } from "@/lib/queries";
import { QUERIES_PER_PHASE_OPTIONS } from "@/lib/tenant-form";
import {
  benchmarkChoices,
  benchmarkProgressText,
  checkedForBenchmark,
  defaultBenchmarkSelection,
  finishedRunId,
} from "@/lib/tenant-state";

const MAX_TENANTS = 6;

export function RunBenchmarkForm() {
  const router = useRouter();
  const [picked, setPicked] = useState<string[] | null>(null);
  const [perPhase, setPerPhase] = useState("10");
  const run = useRunBenchmark();
  // Server-side progress: also shows a run started before this page loaded.
  const { data: progress } = useBenchmarkProgress({ busy: run.isPending });
  const running = run.isPending || !!progress?.running;
  const { data: tenants = [], isLoading: tenantsLoading } = useTenants({ busy: running });
  const choices = benchmarkChoices(tenants);
  const selectable = choices.filter((c) => c.selectable).map((c) => c.tenant.tenant_id);
  const selected = (picked ?? defaultBenchmarkSelection(tenants)).filter((id) =>
    selectable.includes(id)
  );
  const progressText = benchmarkProgressText(progress);
  const checked = checkedForBenchmark(selected, progress);

  // A run this tab only watched (e.g. after a reload) has no mutation
  // callback: announce its end here and offer the report it wrote.
  const previousProgress = useRef(progress);
  useEffect(() => {
    const runId = finishedRunId(previousProgress.current, progress);
    previousProgress.current = progress;
    if (runId === null || run.status !== "idle") return;
    if (runId === "") {
      toast.error("Benchmark ended without a report", {
        description: "It failed on the server; see the API log for the reason.",
      });
      return;
    }
    toast.success("Benchmark finished", {
      description: `rag/reports/${runId}/report.json`,
      duration: 15_000,
      action: { label: "Open report", onClick: () => router.push(`/reports/${runId}`) },
    });
  }, [progress, run.status, router]);

  const submit = () =>
    run.mutate(
      { tenant_ids: selected, queries_per_phase: Number(perPhase) as 5 | 10 | 20 },
      {
        onSuccess: (report) => {
          toast.success("Benchmark written to B2", {
            description: `rag/reports/${report.run_id}/report.json`,
          });
          router.push(`/reports/${report.run_id}`);
        },
        onError: (error) => toast.error("Benchmark failed", { description: error.message }),
      }
    );

  return (
    <Card>
      <CardHeader className="border-b border-border py-4 px-5">
        <CardTitle className="card-title">Run a benchmark</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4 p-5">
        <p className="text-sm text-muted-foreground">
          For each tenant: probe queries warm, park through the full verify-before-drop
          path, the first query restores from B2, then the same probes again.
        </p>
        <fieldset className="space-y-2">
          <legend className="text-sm font-medium">Tenants (up to {MAX_TENANTS})</legend>
          {choices.length === 0 && (
            <p className="text-sm text-muted-foreground">
              {tenantsLoading ? "Loading tenants…" : "No hot or parked tenants yet."}
            </p>
          )}
          {choices.map(({ tenant: t, selectable: canPick }) => (
            <label key={t.tenant_id} className="flex items-center gap-2 text-sm">
              <Checkbox
                checked={checked.includes(t.tenant_id)}
                disabled={
                  !canPick ||
                  running ||
                  (!selected.includes(t.tenant_id) && selected.length >= MAX_TENANTS)
                }
                onCheckedChange={(checked) =>
                  setPicked(
                    checked
                      ? [...selected, t.tenant_id]
                      : selected.filter((id) => id !== t.tenant_id)
                  )
                }
              />
              <span>{t.display_name}</span>
              <StateBadge state={t.state} />
            </label>
          ))}
        </fieldset>
        <div className="flex flex-wrap items-end gap-3">
          <div className="space-y-2">
            <Label htmlFor="per-phase">Queries per phase</Label>
            <Select value={perPhase} onValueChange={setPerPhase}>
              <SelectTrigger id="per-phase" className="w-28">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {QUERIES_PER_PHASE_OPTIONS.map((n) => (
                  <SelectItem key={n} value={String(n)}>
                    {n}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <Button
            onClick={submit}
            disabled={running || selected.length === 0}
            aria-describedby={running ? "benchmark-progress" : undefined}
          >
            {running ? (
              <Loader2 aria-hidden="true" className="h-4 w-4 animate-spin" />
            ) : (
              <Gauge aria-hidden="true" className="h-4 w-4" />
            )}
            {running ? "Benchmarking…" : "Run benchmark"}
          </Button>
        </div>
        {running && (
          <p
            id="benchmark-progress"
            className="text-sm text-muted-foreground"
            aria-live="polite"
            data-testid="benchmark-progress"
          >
            <span className="block">{progressText ?? "Starting the benchmark…"}</span>
            {!run.isPending && (
              <span className="block">
                A benchmark is already running; Run benchmark unlocks when it finishes.
              </span>
            )}
          </p>
        )}
      </CardContent>
    </Card>
  );
}
