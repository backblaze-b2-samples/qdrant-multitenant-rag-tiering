import { ReportsList } from "@/components/reports/reports-list";
import { RunBenchmarkForm } from "@/components/reports/run-benchmark-form";

export default function ReportsPage() {
  return (
    <div className="space-y-8">
      <div className="animate-fade-in border-b border-border pb-5">
        <h1 className="page-title">Latency reports</h1>
        <p className="mt-1.5 max-w-prose text-sm text-muted-foreground">
          What parking costs: warm query latency, restore time from B2, the first query
          after a restore, and the vector memory it frees. Each run is stored in B2 as
          report.json.
        </p>
      </div>
      <div className="grid gap-6 lg:grid-cols-2">
        <RunBenchmarkForm />
        <ReportsList />
      </div>
    </div>
  );
}
