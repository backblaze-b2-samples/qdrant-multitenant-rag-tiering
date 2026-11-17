"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Library } from "lucide-react";
import type { LibraryEntry } from "@qdrant-multitenant-rag-tiering/shared";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { ErrorState } from "@/components/ui/error-state";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { previewHref } from "@/lib/preview-deep-link";
import { useLibrary, useTenants } from "@/lib/queries";
import { formatDate, humanizeBytes } from "@/lib/utils";

const KINDS = ["corpus", "snapshots", "reports"] as const;
const ALL = "all";
const KIND_LABEL: Record<(typeof KINDS)[number], string> = {
  corpus: "Corpus",
  snapshots: "Snapshots",
  reports: "Reports",
};

function group(entries: LibraryEntry[]) {
  const groups = new Map<string, LibraryEntry[]>();
  for (const entry of entries) {
    const kind = KIND_LABEL[entry.kind as keyof typeof KIND_LABEL] ?? entry.kind;
    const label = `${entry.tenant_id ?? "All tenants"} · ${kind}`;
    groups.set(label, [...(groups.get(label) ?? []), entry]);
  }
  return [...groups.entries()];
}

/** The app's own objects in B2, grouped by tenant and kind. */
export function LibraryBrowser() {
  const params = useSearchParams();
  const initialKind = KINDS.find((k) => k === params.get("kind")) ?? ALL;
  const [tenant, setTenant] = useState<string>(ALL);
  const [kind, setKind] = useState<string>(initialKind);
  const { data: tenants = [] } = useTenants();
  const { data, isLoading, error, refetch } = useLibrary(
    tenant === ALL ? undefined : tenant,
    kind === ALL ? undefined : kind
  );
  const groups = useMemo(() => group(data ?? []), [data]);

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap gap-4">
        <div className="space-y-2">
          <Label htmlFor="library-tenant">Tenant</Label>
          <Select value={tenant} onValueChange={setTenant}>
            <SelectTrigger id="library-tenant" className="w-56">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={ALL}>All tenants</SelectItem>
              {tenants.map((t) => (
                <SelectItem key={t.tenant_id} value={t.tenant_id}>
                  {t.display_name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-2">
          <Label htmlFor="library-kind">Kind</Label>
          <Select value={kind} onValueChange={setKind}>
            <SelectTrigger id="library-kind" className="w-40">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={ALL}>All kinds</SelectItem>
              {KINDS.map((k) => (
                <SelectItem key={k} value={k}>
                  {KIND_LABEL[k]}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>

      {isLoading ? (
        <Skeleton className="h-48 w-full" role="status" aria-label="Loading library" />
      ) : error ? (
        <ErrorState error={error} onRetry={() => refetch()} />
      ) : groups.length === 0 ? (
        <EmptyState
          icon={Library}
          title="Nothing here yet"
          description="Seed or create a tenant, park it, or run a benchmark: its objects appear here."
        />
      ) : (
        <div className="grid gap-4 lg:grid-cols-2">
          {groups.map(([label, entries]) => (
            <Card key={label}>
              <CardHeader className="border-b border-border py-3 px-5">
                <CardTitle className="card-title">{label}</CardTitle>
              </CardHeader>
              <CardContent className="p-5">
                <ul className="space-y-1.5 text-sm">
                  {entries.map((entry) => (
                    <li key={entry.key} className="flex items-center justify-between gap-3">
                      <Link
                        href={previewHref(entry.key)}
                        className="min-w-0 truncate font-mono text-xs hover:underline"
                        title={entry.key}
                      >
                        {entry.key.split("/").slice(-1)[0] || entry.key}
                      </Link>
                      <span className="shrink-0 text-xs text-muted-foreground tabular-nums">
                        {humanizeBytes(entry.size_bytes)} · {formatDate(entry.last_modified)}
                      </span>
                    </li>
                  ))}
                </ul>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
