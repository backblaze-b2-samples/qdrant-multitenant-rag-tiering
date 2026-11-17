import { Loader2 } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { stateBadge, type TenantState } from "@/lib/tenant-state";

export function StateBadge({ state }: { state: TenantState }) {
  const badge = stateBadge(state);
  return (
    <Badge
      variant="outline"
      className={cn("gap-1", badge.className)}
      title={badge.description}
      data-state={state}
    >
      {badge.busy && <Loader2 aria-hidden="true" className="animate-spin" />}
      {badge.label}
    </Badge>
  );
}
