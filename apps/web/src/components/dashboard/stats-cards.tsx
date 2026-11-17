"use client";

import { Archive, Boxes, Cpu, Database, FileText, MemoryStick } from "lucide-react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ErrorState } from "@/components/ui/error-state";
import { Skeleton } from "@/components/ui/skeleton";
import { useTieringStats } from "@/lib/queries";
import { humanizeBytes } from "@/lib/utils";

/** Where each tenant lives now, and what that costs in vector memory. */
export function StatsCards() {
  const { data: stats, isLoading, error, refetch } = useTieringStats();

  if (error) {
    return (
      <Card>
        <CardContent className="p-0">
          <ErrorState error={error} onRetry={() => refetch()} />
        </CardContent>
      </Card>
    );
  }

  const cards = [
    { title: "Hot tenants", value: stats ? String(stats.hot) : "", icon: Cpu },
    { title: "Parked in B2", value: stats ? String(stats.parked) : "", icon: Archive },
    { title: "Empty", value: stats ? String(stats.empty) : "", icon: Boxes },
    {
      title: "Vector memory in use (est.)",
      value: stats ? humanizeBytes(stats.vector_bytes_hot) : "",
      icon: MemoryStick,
    },
    {
      title: "Vector memory freed (est.)",
      value: stats ? humanizeBytes(stats.vector_bytes_freed) : "",
      icon: MemoryStick,
    },
    {
      title: "Snapshots in B2",
      value: stats ? humanizeBytes(stats.snapshot_bytes_b2) : "",
      icon: Database,
    },
    {
      title: "Corpus in B2",
      value: stats ? humanizeBytes(stats.corpus_bytes_b2) : "",
      icon: FileText,
    },
  ];

  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4 xl:grid-cols-7">
      {cards.map((card, i) => (
        <Card key={card.title} className={`card-hover animate-fade-in-up stagger-${Math.min(i + 1, 6)}`}>
          <CardHeader className="flex flex-row items-center justify-between pt-4 pb-2 px-4 space-y-0">
            <CardTitle className="text-xs font-semibold text-muted-foreground">{card.title}</CardTitle>
            <div className="stat-icon-wrap">
              <card.icon className="h-4 w-4" />
            </div>
          </CardHeader>
          <CardContent className="pb-5 px-4">
            {isLoading ? <Skeleton className="h-8 w-20" /> : <div className="stat-value">{card.value}</div>}
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
