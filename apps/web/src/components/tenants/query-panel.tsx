"use client";

import { useState } from "react";
import { Loader2, Search } from "lucide-react";
import type { QueryResponse } from "@qdrant-multitenant-rag-tiering/shared";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useQueryTenant } from "@/lib/queries";
import { TOP_K_OPTIONS } from "@/lib/tenant-form";
import { formatMs } from "@/lib/tenant-state";

export function QueryPanel({ tenantId, parked }: { tenantId: string; parked: boolean }) {
  const [query, setQuery] = useState("");
  const [topK, setTopK] = useState("5");
  const [response, setResponse] = useState<QueryResponse | null>(null);
  const run = useQueryTenant(tenantId);

  const submit = (event: React.FormEvent) => {
    event.preventDefault();
    if (!query.trim()) return;
    run.mutate(
      { query: query.trim(), top_k: Number(topK) },
      { onSuccess: setResponse }
    );
  };

  return (
    <Card>
      <CardHeader className="border-b border-border py-4 px-5">
        <CardTitle className="card-title">Query</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4 p-5">
        <form onSubmit={submit} className="flex flex-wrap items-end gap-3">
          <div className="min-w-0 flex-1 space-y-2">
            <Label htmlFor="query-text">Question</Label>
            <Input
              id="query-text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="How much notice is needed to terminate a contract?"
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="top-k">Results</Label>
            <Select value={topK} onValueChange={setTopK}>
              <SelectTrigger id="top-k" className="w-24">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {TOP_K_OPTIONS.map((k) => (
                  <SelectItem key={k} value={String(k)}>
                    {k}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <Button type="submit" disabled={run.isPending || !query.trim()}>
            {run.isPending ? (
              <Loader2 aria-hidden="true" className="h-4 w-4 animate-spin" />
            ) : (
              <Search aria-hidden="true" className="h-4 w-4" />
            )}
            {run.isPending && parked ? "Restoring from B2…" : "Search"}
          </Button>
        </form>
        {run.error && (
          <p className="text-sm text-destructive" role="alert">
            {run.error.message}
          </p>
        )}
        {response && (
          <div className="space-y-3" aria-live="polite">
            <p className="text-sm text-muted-foreground" data-testid="query-latency">
              Search took <span className="font-medium text-foreground">{formatMs(response.latency_ms)}</span>
            </p>
            {response.restored && response.restore && (
              <Alert data-testid="restore-notice">
                <AlertTitle>Restored from B2 before answering</AlertTitle>
                <AlertDescription>
                  Download {formatMs(response.restore.download_ms)}, load into Qdrant{" "}
                  {formatMs(response.restore.load_ms)}, total {formatMs(response.restore.total_ms)}.
                </AlertDescription>
              </Alert>
            )}
            <ol className="space-y-2">
              {response.hits.map((hit) => (
                <li key={`${hit.doc}-${hit.chunk}`} className="rounded-md border border-border p-3">
                  <div className="flex items-center justify-between gap-2 text-xs text-muted-foreground">
                    <span className="font-mono">
                      {hit.doc} #{hit.chunk}
                    </span>
                    <span className="tabular-nums">score {hit.score.toFixed(4)}</span>
                  </div>
                  <p className="mt-1 text-sm">{hit.text}</p>
                </li>
              ))}
            </ol>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
