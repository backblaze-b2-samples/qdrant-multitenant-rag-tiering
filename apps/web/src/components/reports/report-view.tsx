"use client";

import Link from "next/link";
import { Bar, BarChart, CartesianGrid, XAxis, YAxis } from "recharts";
import { FileJson } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  type ChartConfig,
  ChartContainer,
  ChartLegend,
  ChartLegendContent,
  ChartTooltip,
  ChartTooltipContent,
} from "@/components/ui/chart";
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
import { useReport } from "@/lib/queries";
import { allResultsMatch, latencyRows, memoryRows, restorePenalty } from "@/lib/report-chart";
import { formatMs } from "@/lib/tenant-state";
import { formatDate, humanizeBytes } from "@/lib/utils";

const latencyConfig = {
  warmP50: { label: "Warm p50 (ms)", color: "var(--chart-1)" },
  restoreTotal: { label: "Restore from B2 (ms)", color: "var(--chart-3)" },
  postRestoreP50: { label: "Post-restore p50 (ms)", color: "var(--chart-2)" },
} satisfies ChartConfig;

const memoryConfig = {
  estimateMiB: { label: "Vectors + payload freed (MiB, est.)", color: "var(--chart-1)" },
  observedMiB: { label: "Qdrant RSS drop (MiB, observed)", color: "var(--chart-5)" },
} satisfies ChartConfig;

function StatCard({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <Card>
      <CardHeader className="pb-1">
        <CardDescription>{label}</CardDescription>
      </CardHeader>
      <CardContent>{children}</CardContent>
    </Card>
  );
}

export function ReportView({ runId }: { runId: string }) {
  const { data: report, isLoading, error, refetch } = useReport(runId);

  if (isLoading) {
    return <Skeleton className="h-80 w-full" role="status" aria-label="Loading report" />;
  }
  if (error?.isNotFound) {
    return <EmptyState title="Report not found" description={`No report ${runId} in this bucket.`} />;
  }
  if (error || !report) return <ErrorState error={error} onRetry={() => refetch()} />;

  const penalty = restorePenalty(report);
  const matches = allResultsMatch(report);

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4 border-b border-border pb-5">
        <div>
          <h1 className="page-title">Report {report.run_id}</h1>
          <p className="mt-1.5 text-sm text-muted-foreground">
            {formatDate(report.created_at)} · Qdrant {report.qdrant_version ?? "unknown"} ·{" "}
            {report.embedding_model}
          </p>
        </div>
        <Button asChild size="sm" variant="outline" className="h-8">
          <Link href="/library?kind=reports">
            <FileJson aria-hidden="true" className="h-3.5 w-3.5" />
            report.json in B2
          </Link>
        </Button>
      </div>

      <div className="grid gap-4 sm:grid-cols-3">
        <StatCard label="Tenants measured">
          <div className="stat-value">{report.tenants.length}</div>
        </StatCard>
        <StatCard label="First query after park vs warm p50">
          <div className="stat-value">{penalty === null ? "—" : `${penalty}×`}</div>
        </StatCard>
        <StatCard label="Results after restore">
          <Badge variant={matches ? "secondary" : "destructive"} data-testid="results-match">
            {matches ? "Identical to warm" : "Changed"}
          </Badge>
        </StatCard>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader className="border-b border-border py-4 px-5">
            <CardTitle className="card-title">Latency per tenant</CardTitle>
            <CardDescription className="text-xs">Warm vs restore vs post-restore</CardDescription>
          </CardHeader>
          <CardContent className="p-5">
            <ChartContainer config={latencyConfig} className="h-[260px] w-full">
              <BarChart data={latencyRows(report)} margin={{ top: 8, right: 4, left: 0, bottom: 0 }}>
                <CartesianGrid vertical={false} strokeDasharray="3 3" stroke="var(--border)" />
                <XAxis dataKey="tenant" tickLine={false} axisLine={false} fontSize={11} />
                <YAxis tickLine={false} axisLine={false} fontSize={11} width={48} />
                <ChartTooltip content={<ChartTooltipContent />} />
                <ChartLegend content={<ChartLegendContent />} />
                <Bar dataKey="warmP50" fill="var(--color-warmP50)" radius={[3, 3, 0, 0]} />
                <Bar dataKey="restoreTotal" fill="var(--color-restoreTotal)" radius={[3, 3, 0, 0]} />
                <Bar dataKey="postRestoreP50" fill="var(--color-postRestoreP50)" radius={[3, 3, 0, 0]} />
              </BarChart>
            </ChartContainer>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="border-b border-border py-4 px-5">
            <CardTitle className="card-title">Memory freed by parking</CardTitle>
            <CardDescription className="text-xs">
              The estimate is deterministic; observed RSS may lag the allocator
            </CardDescription>
          </CardHeader>
          <CardContent className="p-5">
            <ChartContainer config={memoryConfig} className="h-[260px] w-full">
              <BarChart data={memoryRows(report)} margin={{ top: 8, right: 4, left: 0, bottom: 0 }}>
                <CartesianGrid vertical={false} strokeDasharray="3 3" stroke="var(--border)" />
                <XAxis dataKey="tenant" tickLine={false} axisLine={false} fontSize={11} />
                <YAxis tickLine={false} axisLine={false} fontSize={11} width={48} />
                <ChartTooltip content={<ChartTooltipContent />} />
                <ChartLegend content={<ChartLegendContent />} />
                <Bar dataKey="estimateMiB" fill="var(--color-estimateMiB)" radius={[3, 3, 0, 0]} />
                <Bar dataKey="observedMiB" fill="var(--color-observedMiB)" radius={[3, 3, 0, 0]} />
              </BarChart>
            </ChartContainer>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader className="border-b border-border py-4 px-5">
          <CardTitle className="card-title">Figures</CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Tenant</TableHead>
                <TableHead className="text-right">Points</TableHead>
                <TableHead className="text-right">Warm p50 / p95</TableHead>
                <TableHead className="text-right">Snapshot</TableHead>
                <TableHead className="text-right">Upload</TableHead>
                <TableHead className="text-right">Restore (download + load)</TableHead>
                <TableHead className="text-right">First query</TableHead>
                <TableHead className="text-right">Post p50 / p95</TableHead>
                <TableHead>Match</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {report.tenants.map((t) => (
                <TableRow key={t.tenant_id}>
                  <TableCell className="font-mono text-xs">{t.tenant_id}</TableCell>
                  <TableCell className="text-right tabular-nums">{t.point_count}</TableCell>
                  <TableCell className="text-right tabular-nums">
                    {formatMs(t.warm.p50_ms)} / {formatMs(t.warm.p95_ms)}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">
                    {humanizeBytes(t.snapshot_bytes)}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">
                    {formatMs(t.snapshot_upload_ms)}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">
                    {formatMs(t.restore.total_ms)} ({formatMs(t.restore.download_ms)} +{" "}
                    {formatMs(t.restore.load_ms)})
                  </TableCell>
                  <TableCell className="text-right tabular-nums">
                    {formatMs(t.first_query_after_restore_ms)}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">
                    {formatMs(t.post_restore.p50_ms)} / {formatMs(t.post_restore.p95_ms)}
                  </TableCell>
                  <TableCell>{t.results_match ? "yes" : "no"}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}
