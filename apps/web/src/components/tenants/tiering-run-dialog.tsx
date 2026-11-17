"use client";

import { useState } from "react";
import { Loader2, Timer } from "lucide-react";
import { toast } from "sonner";
import type { TieringRunResult } from "@qdrant-multitenant-rag-tiering/shared";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { useRunTiering, useTieringPolicy } from "@/lib/queries";
import { idleOptionsFor } from "@/lib/tenant-form";

/** Run the idle policy now: dry run by default, so nothing moves until asked. */
export function TieringRunDialog() {
  const { data: policy } = useTieringPolicy();
  const [idle, setIdle] = useState<string | null>(null);
  const [dryRun, setDryRun] = useState(true);
  const [result, setResult] = useState<TieringRunResult | null>(null);
  const run = useRunTiering();
  const options = idleOptionsFor(policy?.idle_seconds);
  const idleValue = idle ?? String(policy?.idle_seconds ?? 604_800);

  const submit = () =>
    run.mutate(
      { idle_seconds: Number(idleValue), dry_run: dryRun },
      {
        onSuccess: (r) => {
          setResult(r);
          if (!r.dry_run) toast.success(`Parked ${r.parked.length} tenant(s) in B2`);
        },
        onError: (error) => toast.error("Tiering run failed", { description: error.message }),
      }
    );

  return (
    <Dialog onOpenChange={(open) => !open && setResult(null)}>
      <DialogTrigger asChild>
        <Button size="sm" variant="outline" className="h-8">
          <Timer aria-hidden="true" className="h-3.5 w-3.5" />
          Run tiering sweep
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Run tiering sweep</DialogTitle>
          <DialogDescription>
            Hot tenants with no query or write for the idle threshold are snapshotted,
            uploaded to B2, verified, and only then dropped from Qdrant.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="idle-threshold">Idle threshold</Label>
            <Select value={idleValue} onValueChange={setIdle}>
              <SelectTrigger id="idle-threshold" className="w-48">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {options.map((o) => (
                  <SelectItem key={o.seconds} value={String(o.seconds)}>
                    {o.label}
                    {o.seconds === policy?.idle_seconds ? " (policy)" : ""}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="flex items-center justify-between rounded-md border border-border p-3">
            <div>
              <Label htmlFor="dry-run">Dry run</Label>
              <p className="text-xs text-muted-foreground">List candidates without parking them.</p>
            </div>
            <Switch id="dry-run" checked={dryRun} onCheckedChange={setDryRun} />
          </div>
          {result && (
            <div className="space-y-1 rounded-md border border-border bg-muted/30 p-3 text-sm" aria-live="polite">
              <p>
                <span className="font-medium">Candidates:</span>{" "}
                {result.candidates.length ? result.candidates.join(", ") : "none"}
              </p>
              {!result.dry_run && (
                <p>
                  <span className="font-medium">Parked:</span>{" "}
                  {result.parked.length ? result.parked.join(", ") : "none"}
                </p>
              )}
              {result.skipped.map((s) => (
                <p key={s.tenant_id} className="text-destructive">
                  Skipped {s.tenant_id}: {s.reason}
                </p>
              ))}
            </div>
          )}
        </div>
        <DialogFooter>
          <Button onClick={submit} disabled={run.isPending}>
            {run.isPending && <Loader2 aria-hidden="true" className="h-4 w-4 animate-spin" />}
            {dryRun ? "Find candidates" : "Park idle tenants"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
