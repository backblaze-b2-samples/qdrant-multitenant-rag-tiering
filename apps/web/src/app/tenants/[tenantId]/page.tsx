import { TenantDetailView } from "@/components/tenants/tenant-detail";

export default async function TenantPage({
  params,
}: {
  params: Promise<{ tenantId: string }>;
}) {
  const { tenantId } = await params;
  return <TenantDetailView tenantId={decodeURIComponent(tenantId)} />;
}
