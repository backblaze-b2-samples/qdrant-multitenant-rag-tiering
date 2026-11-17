import { z } from "zod";

import { THEME_OPTIONS } from "@/lib/theme-preference";

/**
 * Validation for the Settings form (`components/settings/settings-form.tsx`).
 *
 * Theme is the only editable preference: the tiering policy is server
 * configuration (environment variables) and is shown read-only beside it.
 * Kept outside the component so it is unit-tested without rendering the form.
 */
export const settingsSchema = z.object({
  theme: z.enum(THEME_OPTIONS),
});

export type SettingsValues = z.infer<typeof settingsSchema>;
