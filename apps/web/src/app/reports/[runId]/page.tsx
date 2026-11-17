import { ReportView } from "@/components/reports/report-view";

export default async function ReportPage({ params }: { params: Promise<{ runId: string }> }) {
  const { runId } = await params;
  return <ReportView runId={decodeURIComponent(runId)} />;
}
