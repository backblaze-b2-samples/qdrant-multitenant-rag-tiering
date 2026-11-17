"use client";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useTenantSnapshots } from "@/lib/queries";
import { formatDate, humanizeBytes } from "@/lib/utils";

export function SnapshotHistory({ tenantId }: { tenantId: string }) {
  const { data, isLoading } = useTenantSnapshots(tenantId);

  return (
    <Card>
      <CardHeader className="border-b border-border py-4 px-5">
        <CardTitle className="card-title">Snapshots in B2</CardTitle>
      </CardHeader>
      <CardContent className="p-5">
        {isLoading ? (
          <Skeleton className="h-16 w-full" />
        ) : !data || data.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            No snapshots yet. Park the tenant to write the first one.
          </p>
        ) : (
          <ul className="space-y-2 text-sm">
            {data.map((s) => (
              <li key={s.key} className="flex flex-wrap items-center justify-between gap-2">
                <span className="min-w-0 break-all font-mono text-xs">{s.key.split("/").pop()}</span>
                <span className="flex items-center gap-2 text-muted-foreground">
                  {s.is_latest && <Badge variant="secondary">latest.json</Badge>}
                  {humanizeBytes(s.size_bytes)} · {formatDate(s.created_at)}
                </span>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}
