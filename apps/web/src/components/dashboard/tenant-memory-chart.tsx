"use client";

import { useMemo } from "react";
import Link from "next/link";
import { Bar, BarChart, CartesianGrid, Cell, XAxis, YAxis } from "recharts";
import { Boxes } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  type ChartConfig,
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
} from "@/components/ui/chart";
import { EmptyState } from "@/components/ui/empty-state";
import { ErrorState } from "@/components/ui/error-state";
import { Skeleton } from "@/components/ui/skeleton";
import { useTenants } from "@/lib/queries";
import { truncateLabel } from "@/lib/utils";

const chartConfig = {
  kib: { label: "Vector memory (KiB, est.)", color: "var(--chart-1)" },
} satisfies ChartConfig;

/**
 * Per-tenant vector footprint. Hot bars are memory in use now; parked bars
 * (muted) are what each parked tenant would cost if it were loaded again.
 */
export function TenantMemoryChart() {
  const { data: tenants, isLoading, error, refetch } = useTenants();
  const rows = useMemo(
    () =>
      (tenants ?? []).map((t) => ({
        tenant: t.tenant_id,
        kib: Math.round(t.vector_bytes_estimate / 102.4) / 10,
        hot: t.state === "hot",
      })),
    [tenants]
  );

  return (
    <Card>
      <CardHeader className="border-b border-border py-4 px-5">
        <CardTitle className="card-title">Vector footprint per tenant</CardTitle>
        <CardDescription className="text-xs">Solid: hot in Qdrant. Faded: parked in B2.</CardDescription>
      </CardHeader>
      <CardContent className="p-5">
        {isLoading ? (
          <Skeleton className="h-[240px] w-full" />
        ) : error ? (
          <ErrorState error={error} onRetry={() => refetch()} />
        ) : rows.length === 0 ? (
          <EmptyState
            icon={Boxes}
            title="No tenants yet"
            description="Seed the demo tenants to see their footprint."
            action={
              <Button asChild size="sm" variant="outline">
                <Link href="/tenants">Go to tenants</Link>
              </Button>
            }
          />
        ) : (
          <ChartContainer config={chartConfig} className="h-[280px] w-full">
            <BarChart data={rows} margin={{ top: 8, right: 4, left: 0, bottom: 0 }}>
              <CartesianGrid vertical={false} strokeDasharray="3 3" stroke="var(--border)" />
              {/* interval 0: label every bar (recharts otherwise skips ticks
                  that would collide); angled and shortened so they fit. */}
              <XAxis
                dataKey="tenant"
                tickLine={false}
                axisLine={false}
                fontSize={11}
                interval={0}
                angle={-35}
                textAnchor="end"
                height={70}
                tickFormatter={(id: string) => truncateLabel(id, 16)}
              />
              <YAxis tickLine={false} axisLine={false} fontSize={11} width={40} />
              <ChartTooltip content={<ChartTooltipContent />} />
              <Bar dataKey="kib" radius={[4, 4, 0, 0]}>
                {rows.map((row) => (
                  <Cell
                    key={row.tenant}
                    fill="var(--color-kib)"
                    fillOpacity={row.hot ? 0.95 : 0.3}
                  />
                ))}
              </Bar>
            </BarChart>
          </ChartContainer>
        )}
      </CardContent>
    </Card>
  );
}
