import { describe, expect, it } from "vitest";

import { IDLE_OPTIONS, idleOptionsFor, tenantFormSchema } from "./tenant-form";

describe("tenantFormSchema", () => {
  it("accepts ids the API accepts", () => {
    for (const id of ["ab", "acme-legal", "x".repeat(40)]) {
      expect(tenantFormSchema.safeParse({ tenant_id: id, display_name: "X" }).success).toBe(true);
    }
  });

  it("rejects ids the API rejects", () => {
    for (const id of ["a", "Acme", "-ab", "ab-", "a_b", "x".repeat(41)]) {
      expect(tenantFormSchema.safeParse({ tenant_id: id, display_name: "X" }).success).toBe(false);
    }
  });
});

describe("idleOptionsFor", () => {
  it("returns the fixed list when the policy value is one of them", () => {
    expect(idleOptionsFor(604_800)).toBe(IDLE_OPTIONS);
  });

  it("adds a non-standard policy value in order", () => {
    const options = idleOptionsFor(120);
    expect(options.map((o) => o.seconds)).toEqual([30, 120, 300, 3600, 86_400, 604_800]);
  });
});
