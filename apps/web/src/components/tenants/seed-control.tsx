"use client";

import { useState } from "react";
import { Loader2, Sprout } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useSeedTenants } from "@/lib/queries";
import { SEED_COUNT_OPTIONS } from "@/lib/tenant-form";

/** Seed N synthetic tenants on distinct subjects (written into B2, then indexed). */
export function SeedControl() {
  const [count, setCount] = useState("4");
  const seed = useSeedTenants();

  return (
    <div className="flex items-center gap-2">
      <Select value={count} onValueChange={setCount}>
        <SelectTrigger className="h-8 w-28" aria-label="Number of demo tenants">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {SEED_COUNT_OPTIONS.map((n) => (
            <SelectItem key={n} value={String(n)}>
              {n} tenants
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      <Button
        size="sm"
        variant="outline"
        className="h-8"
        disabled={seed.isPending}
        onClick={() =>
          seed.mutate(Number(count), {
            onSuccess: (result) =>
              toast.success(`Seeded ${result.created.length} tenant(s)`, {
                description: result.skipped.length
                  ? `Already present: ${result.skipped.join(", ")}`
                  : "Corpus written to B2 and indexed into Qdrant.",
              }),
            onError: (error) => toast.error("Seeding failed", { description: error.message }),
          })
        }
      >
        {seed.isPending ? (
          <Loader2 aria-hidden="true" className="h-3.5 w-3.5 animate-spin" />
        ) : (
          <Sprout aria-hidden="true" className="h-3.5 w-3.5" />
        )}
        {seed.isPending ? "Seeding…" : "Seed demo tenants"}
      </Button>
    </div>
  );
}
