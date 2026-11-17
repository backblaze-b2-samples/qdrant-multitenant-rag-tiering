import { zodResolver } from "@hookform/resolvers/zod";
import { describe, expect, it } from "vitest";

import { settingsSchema, type SettingsValues } from "@/lib/settings-schema";

async function resolve(values: unknown) {
  const resolver = zodResolver(settingsSchema);
  return resolver(values as SettingsValues, undefined, {
    fields: {},
    shouldUseNativeValidation: false,
  });
}

describe("settingsSchema", () => {
  it("accepts every theme option through the form resolver", async () => {
    for (const theme of ["light", "dark", "system"] as const) {
      const result = await resolve({ theme });
      expect(result.errors).toEqual({});
      expect(result.values).toEqual({ theme });
    }
  });

  it("rejects an unknown theme", () => {
    expect(settingsSchema.safeParse({ theme: "sepia" }).success).toBe(false);
  });
});
