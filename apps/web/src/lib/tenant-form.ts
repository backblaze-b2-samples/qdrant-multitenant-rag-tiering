import { z } from "zod";

/**
 * Create-tenant form rules, mirroring the API (`TENANT_ID_PATTERN` in
 * services/api/app/types/tenants.py) so a bad id is caught before the request.
 */
export const TENANT_ID_RE = /^[a-z0-9][a-z0-9-]{0,38}[a-z0-9]$/;

export const tenantFormSchema = z.object({
  tenant_id: z
    .string()
    .regex(
      TENANT_ID_RE,
      "Use lowercase letters, digits and hyphens, 2 to 40 characters"
    ),
  display_name: z.string().trim().min(1, "Give the tenant a display name").max(80),
});

export type TenantFormValues = z.infer<typeof tenantFormSchema>;

export const TOP_K_OPTIONS = [3, 5, 10] as const;
export const SEED_COUNT_OPTIONS = [2, 4, 6] as const;
export const QUERIES_PER_PHASE_OPTIONS = [5, 10, 20] as const;
export const KEEP_LAST_OPTIONS = [1, 2, 3] as const;
export const IDLE_OPTIONS: { label: string; seconds: number }[] = [
  { label: "30 s", seconds: 30 },
  { label: "5 min", seconds: 300 },
  { label: "1 h", seconds: 3600 },
  { label: "1 day", seconds: 86_400 },
  { label: "7 days", seconds: 604_800 },
];

/** The idle options, plus the server policy's own value when it is not one of them. */
export function idleOptionsFor(policySeconds: number | undefined) {
  if (policySeconds === undefined || IDLE_OPTIONS.some((o) => o.seconds === policySeconds)) {
    return IDLE_OPTIONS;
  }
  return [...IDLE_OPTIONS, { label: `${policySeconds} s (policy)`, seconds: policySeconds }].sort(
    (a, b) => a.seconds - b.seconds
  );
}
