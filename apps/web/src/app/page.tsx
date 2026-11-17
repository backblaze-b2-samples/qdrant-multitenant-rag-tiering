import Link from "next/link";
import { Boxes } from "lucide-react";

import { Button } from "@/components/ui/button";
import { StatsCards } from "@/components/dashboard/stats-cards";
import { TenantMemoryChart } from "@/components/dashboard/tenant-memory-chart";
import { ReportsList } from "@/components/reports/reports-list";

export default function DashboardPage() {
  return (
    <div className="space-y-8">
      <div className="animate-fade-in border-b border-border pb-5 flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="page-title">Dashboard</h1>
          <p className="text-sm text-muted-foreground mt-1.5">
            Vector memory spent on hot tenants, and what parking idle tenants in
            Backblaze B2 has freed.
          </p>
        </div>
        <Button asChild size="sm" className="h-8">
          <Link href="/tenants">
            <Boxes className="h-3.5 w-3.5" />
            Manage tenants
          </Link>
        </Button>
      </div>
      <StatsCards />
      <div className="grid gap-6 lg:grid-cols-2">
        <div className="animate-fade-in-up stagger-3">
          <TenantMemoryChart />
        </div>
        <div className="animate-fade-in-up stagger-4">
          <ReportsList limit={5} />
        </div>
      </div>
    </div>
  );
}
