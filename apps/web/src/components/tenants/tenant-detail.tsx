"use client";

import Link from "next/link";
import { ArchiveRestore, Boxes, CloudUpload, Loader2 } from "lucide-react";
import { toast } from "sonner";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { ErrorState } from "@/components/ui/error-state";
import { Skeleton } from "@/components/ui/skeleton";
import { DeleteTenant } from "@/components/tenants/delete-tenant";
import { EditTenantSheet } from "@/components/tenants/edit-tenant-sheet";
import { QueryPanel } from "@/components/tenants/query-panel";
import { SnapshotHistory } from "@/components/tenants/snapshot-history";
import { StateBadge } from "@/components/tenants/state-badge";
import { previewHref } from "@/lib/preview-deep-link";
import { useParkTenant, useRestoreTenant, useTenant } from "@/lib/queries";
import { formatAge, formatMs } from "@/lib/tenant-state";
import { formatDate, humanizeBytes } from "@/lib/utils";

function Fact({ label, value }: { label: string; value: string | number }) {
  return (
    <div>
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className="mt-0.5 font-medium tabular-nums">{value}</dd>
    </div>
  );
}

export function TenantDetailView({ tenantId }: { tenantId: string }) {
  const { data: tenant, isLoading, error, refetch } = useTenant(tenantId);
  const park = useParkTenant(tenantId);
  const restore = useRestoreTenant(tenantId);

  if (isLoading) {
    return <Skeleton className="h-64 w-full" role="status" aria-label="Loading tenant" />;
  }
  if (error?.isNotFound) {
    return (
      <EmptyState
        icon={Boxes}
        title="Tenant not found"
        description={`No tenant ${tenantId} exists in this bucket.`}
        action={
          <Button asChild size="sm" variant="outline">
            <Link href="/tenants">All tenants</Link>
          </Button>
        }
      />
    );
  }
  if (error || !tenant) {
    return <ErrorState error={error} onRetry={() => refetch()} />;
  }

  const busy = park.isPending || restore.isPending;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4 border-b border-border pb-5">
        <div className="min-w-0">
          <div className="flex items-center gap-3">
            <h1 className="page-title">{tenant.display_name}</h1>
            <StateBadge state={tenant.state} />
          </div>
          <p className="mt-1.5 font-mono text-xs text-muted-foreground">
            {tenant.tenant_id} · collection tenant_{tenant.tenant_id}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button
            size="sm"
            className="h-8"
            disabled={tenant.state !== "hot" || busy}
            onClick={() =>
              park.mutate(undefined, {
                onSuccess: (r) =>
                  r.verified
                    ? toast.success("Parked in B2", {
                        description: `Snapshot verified (${humanizeBytes(r.manifest?.size_bytes ?? 0)}); collection dropped, ~${humanizeBytes(r.vector_bytes_freed)} of vectors freed.`,
                      })
                    : toast.error("Not parked; tenant stays hot", { description: r.reason ?? undefined }),
                onError: (e) => toast.error("Park failed", { description: e.message }),
              })
            }
          >
            {park.isPending ? (
              <Loader2 aria-hidden="true" className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <CloudUpload aria-hidden="true" className="h-3.5 w-3.5" />
            )}
            Park now
          </Button>
          <Button
            size="sm"
            variant="outline"
            className="h-8"
            disabled={tenant.state !== "parked" || busy}
            onClick={() =>
              restore.mutate(undefined, {
                onSuccess: (r) =>
                  toast.success("Restored from B2", {
                    description: `${r.point_count} points in ${formatMs(r.timing.total_ms)}.`,
                  }),
                onError: (e) => toast.error("Restore failed", { description: e.message }),
              })
            }
          >
            {restore.isPending ? (
              <Loader2 aria-hidden="true" className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <ArchiveRestore aria-hidden="true" className="h-3.5 w-3.5" />
            )}
            Restore now
          </Button>
          <EditTenantSheet tenant={tenant} />
        </div>
      </div>

      {tenant.snapshot_stale && (
        <Alert>
          <AlertDescription>
            Documents changed after the latest snapshot. The next park writes a fresh one;
            until then latest.json still points at the older snapshot.
          </AlertDescription>
        </Alert>
      )}

      <Card>
        <CardContent className="p-5">
          <dl className="grid gap-4 sm:grid-cols-3 lg:grid-cols-6">
            <Fact label="Points" value={tenant.point_count} />
            <Fact label="Documents" value={tenant.document_count} />
            <Fact label="Vector memory (est.)" value={humanizeBytes(tenant.vector_bytes_estimate)} />
            <Fact label="Last query" value={formatAge(tenant.last_query_at)} />
            <Fact
              label="Latest snapshot"
              value={tenant.snapshot_size_bytes === null ? "none" : humanizeBytes(tenant.snapshot_size_bytes)}
            />
            <Fact
              label="Snapshot taken"
              value={tenant.snapshot_created_at ? formatDate(tenant.snapshot_created_at) : "never"}
            />
          </dl>
        </CardContent>
      </Card>

      <QueryPanel tenantId={tenantId} parked={tenant.state === "parked"} />

      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader className="border-b border-border py-4 px-5">
            <CardTitle className="card-title">Documents in B2</CardTitle>
          </CardHeader>
          <CardContent className="p-5">
            <ul className="space-y-2 text-sm">
              {tenant.documents.map((doc) => (
                <li key={doc.filename} className="flex items-center justify-between gap-2">
                  <Link href={previewHref(doc.key)} className="font-mono text-xs hover:underline">
                    {doc.filename}
                  </Link>
                  <span className="text-muted-foreground tabular-nums">
                    {humanizeBytes(doc.size_bytes)} · {doc.chunks} chunk{doc.chunks === 1 ? "" : "s"}
                  </span>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
        <SnapshotHistory tenantId={tenantId} />
      </div>

      <DeleteTenant tenantId={tenantId} />
    </div>
  );
}
