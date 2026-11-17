"use client";

import { useState } from "react";
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
import { useRunBenchmark, useTenants } from "@/lib/queries";
import { QUERIES_PER_PHASE_OPTIONS } from "@/lib/tenant-form";
import { defaultBenchmarkSelection } from "@/lib/tenant-state";

const MAX_TENANTS = 6;

export function RunBenchmarkForm() {
  const router = useRouter();
  const { data: tenants = [] } = useTenants();
  const [picked, setPicked] = useState<string[] | null>(null);
  const [perPhase, setPerPhase] = useState("10");
  const run = useRunBenchmark();
  const selected = picked ?? defaultBenchmarkSelection(tenants);
  const eligible = tenants.filter((t) => t.state === "hot" || t.state === "parked");

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
          {eligible.length === 0 && (
            <p className="text-sm text-muted-foreground">No hot or parked tenants yet.</p>
          )}
          {eligible.map((t) => (
            <label key={t.tenant_id} className="flex items-center gap-2 text-sm">
              <Checkbox
                checked={selected.includes(t.tenant_id)}
                disabled={!selected.includes(t.tenant_id) && selected.length >= MAX_TENANTS}
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
          <Button onClick={submit} disabled={run.isPending || selected.length === 0}>
            {run.isPending ? (
              <Loader2 aria-hidden="true" className="h-4 w-4 animate-spin" />
            ) : (
              <Gauge aria-hidden="true" className="h-4 w-4" />
            )}
            {run.isPending ? "Benchmarking…" : "Run benchmark"}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
