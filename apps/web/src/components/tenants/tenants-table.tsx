"use client";

import Link from "next/link";
import { Boxes } from "lucide-react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { ErrorState } from "@/components/ui/error-state";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { StateBadge } from "@/components/tenants/state-badge";
import { SeedControl } from "@/components/tenants/seed-control";
import { useTenants } from "@/lib/queries";
import { formatAge, vectorMemoryText } from "@/lib/tenant-state";
import { humanizeBytes } from "@/lib/utils";

export function TenantsTable() {
  const { data: tenants, isLoading, error, refetch } = useTenants();

  return (
    <Card>
      <CardHeader className="border-b border-border py-4 px-5">
        <CardTitle className="card-title">All tenants</CardTitle>
      </CardHeader>
      <CardContent className="p-0">
        {isLoading ? (
          <div className="space-y-2 p-5" role="status" aria-label="Loading tenants">
            {[0, 1, 2].map((i) => (
              <Skeleton key={i} className="h-9 w-full" />
            ))}
          </div>
        ) : error ? (
          <ErrorState error={error} onRetry={() => refetch()} />
        ) : !tenants || tenants.length === 0 ? (
          <EmptyState
            icon={Boxes}
            title="No tenants yet"
            description="Seed the demo tenants (distinct subjects, no download needed) or create one from your own text files."
            action={<SeedControl />}
          />
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Tenant</TableHead>
                <TableHead>State</TableHead>
                <TableHead className="text-right">Points</TableHead>
                <TableHead className="text-right">Docs</TableHead>
                <TableHead className="text-right">Vector memory in Qdrant (est.)</TableHead>
                <TableHead>Last query</TableHead>
                <TableHead className="text-right">Snapshot in B2</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {tenants.map((t) => (
                <TableRow key={t.tenant_id}>
                  <TableCell>
                    <Link
                      href={`/tenants/${t.tenant_id}`}
                      className="font-medium hover:underline"
                    >
                      {t.display_name}
                    </Link>
                    <div className="font-mono text-xs text-muted-foreground">{t.tenant_id}</div>
                  </TableCell>
                  <TableCell>
                    <StateBadge state={t.state} />
                  </TableCell>
                  <TableCell className="text-right tabular-nums">{t.point_count}</TableCell>
                  <TableCell className="text-right tabular-nums">{t.document_count}</TableCell>
                  <TableCell className="text-right tabular-nums">
                    {vectorMemoryText(t)}
                  </TableCell>
                  <TableCell className="text-muted-foreground">{formatAge(t.last_query_at)}</TableCell>
                  <TableCell className="text-right tabular-nums">
                    {t.snapshot_size_bytes === null ? "—" : humanizeBytes(t.snapshot_size_bytes)}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent>
    </Card>
  );
}
