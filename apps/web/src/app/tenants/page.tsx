import { NewTenantDialog } from "@/components/tenants/new-tenant-dialog";
import { PruneDialog } from "@/components/tenants/prune-dialog";
import { SeedControl } from "@/components/tenants/seed-control";
import { TenantsTable } from "@/components/tenants/tenants-table";
import { TieringRunDialog } from "@/components/tenants/tiering-run-dialog";

export default function TenantsPage() {
  return (
    <div className="space-y-8">
      <div className="animate-fade-in flex flex-wrap items-start justify-between gap-4 border-b border-border pb-5">
        <div className="min-w-0">
          <h1 className="page-title">Tenants</h1>
          <p className="mt-1.5 max-w-prose text-sm text-muted-foreground">
            One Qdrant collection per tenant while it is hot; a verified snapshot in
            B2 while it is parked. The first query to a parked tenant restores it.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <SeedControl />
          <TieringRunDialog />
          <PruneDialog />
          <NewTenantDialog />
        </div>
      </div>
      <div className="animate-fade-in-up stagger-2">
        <TenantsTable />
      </div>
    </div>
  );
}
