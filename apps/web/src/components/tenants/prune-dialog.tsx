"use client";

import { useState } from "react";
import { Eraser, Loader2 } from "lucide-react";
import { toast } from "sonner";
import type { PruneResult } from "@qdrant-multitenant-rag-tiering/shared";

import { Alert, AlertDescription } from "@/components/ui/alert";
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
import { usePruneSnapshots, useTieringPolicy } from "@/lib/queries";
import { KEEP_LAST_OPTIONS } from "@/lib/tenant-form";

export function PruneDialog() {
  const { data: policy } = useTieringPolicy();
  const [keepLast, setKeepLast] = useState("1");
  const [apply, setApply] = useState(false);
  const [result, setResult] = useState<PruneResult | null>(null);
  const prune = usePruneSnapshots();
  const enabled = policy?.prune_enabled ?? false;

  const submit = () =>
    prune.mutate(
      { keep_last: Number(keepLast), apply },
      {
        onSuccess: (r) => {
          setResult(r);
          if (r.applied) toast.success(`Deleted ${r.deleted.length} superseded snapshot(s)`);
        },
        onError: (error) => toast.error("Prune refused", { description: error.message }),
      }
    );

  return (
    <Dialog onOpenChange={(open) => !open && setResult(null)}>
      <DialogTrigger asChild>
        <Button size="sm" variant="outline" className="h-8">
          <Eraser aria-hidden="true" className="h-3.5 w-3.5" />
          Prune snapshots
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Prune superseded snapshots</DialogTitle>
          <DialogDescription>
            Keeps the newest snapshots per tenant. The snapshot a tenant&apos;s
            latest.json points at is never deleted.
          </DialogDescription>
        </DialogHeader>
        {!enabled && (
          <Alert>
            <AlertDescription>
              Pruning is disabled on the server. Set SNAPSHOT_PRUNE_ENABLED=true and
              restart the API to allow it.
            </AlertDescription>
          </Alert>
        )}
        <div className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="keep-last">Snapshots to keep per tenant</Label>
            <Select value={keepLast} onValueChange={setKeepLast}>
              <SelectTrigger id="keep-last" className="w-32">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {KEEP_LAST_OPTIONS.map((n) => (
                  <SelectItem key={n} value={String(n)}>
                    {n}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="flex items-center justify-between rounded-md border border-border p-3">
            <div>
              <Label htmlFor="prune-apply">Delete for real</Label>
              <p className="text-xs text-muted-foreground">Off lists candidates only.</p>
            </div>
            <Switch id="prune-apply" checked={apply} onCheckedChange={setApply} />
          </div>
          {result && (
            <div className="rounded-md border border-border bg-muted/30 p-3 text-sm" aria-live="polite">
              <p className="font-medium">
                {result.applied ? `Deleted ${result.deleted.length}` : `${result.candidates.length} candidate(s)`}
              </p>
              <ul className="mt-1 max-h-32 overflow-auto font-mono text-xs">
                {(result.applied ? result.deleted : result.candidates).map((key) => (
                  <li key={key} className="break-all">
                    {key}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
        <DialogFooter>
          <Button onClick={submit} disabled={prune.isPending || !enabled} variant={apply ? "destructive" : "default"}>
            {prune.isPending && <Loader2 aria-hidden="true" className="h-4 w-4 animate-spin" />}
            {apply ? "Delete snapshots" : "List candidates"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
