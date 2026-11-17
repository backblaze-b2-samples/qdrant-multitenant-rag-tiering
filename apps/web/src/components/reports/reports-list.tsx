"use client";

import Link from "next/link";
import { BarChart3 } from "lucide-react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { ErrorState } from "@/components/ui/error-state";
import { Skeleton } from "@/components/ui/skeleton";
import { useReports } from "@/lib/queries";
import { formatDate } from "@/lib/utils";

export function ReportsList({ limit }: { limit?: number }) {
  const { data, isLoading, error, refetch } = useReports();
  const reports = limit ? (data ?? []).slice(0, limit) : (data ?? []);

  return (
    <Card>
      <CardHeader className="border-b border-border py-4 px-5">
        <CardTitle className="card-title">Latency reports</CardTitle>
      </CardHeader>
      <CardContent className="p-5">
        {isLoading ? (
          <Skeleton className="h-24 w-full" />
        ) : error ? (
          <ErrorState error={error} onRetry={() => refetch()} />
        ) : reports.length === 0 ? (
          <EmptyState
            icon={BarChart3}
            title="No reports yet"
            description="Run a benchmark to measure warm, restore and post-restore latency."
          />
        ) : (
          <ul className="divide-y divide-border text-sm">
            {reports.map((r) => (
              <li key={r.run_id} className="flex items-center justify-between gap-2 py-2">
                <Link href={`/reports/${r.run_id}`} className="font-mono text-xs hover:underline">
                  {r.run_id}
                </Link>
                <span className="text-muted-foreground">
                  {r.tenant_count} tenant{r.tenant_count === 1 ? "" : "s"} · {formatDate(r.created_at)}
                </span>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}
