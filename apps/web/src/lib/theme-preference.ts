/**
 * The one preference this app genuinely honours.
 *
 * `next-themes` owns and persists the theme, so there is nothing to store here,
 * only the option list and the coercion the Settings form needs.
 *
 * The rest of the Settings page is a read-only view of the server's tiering
 * policy, which is configured by environment variables, not in the browser.
 * See `docs/features/settings.md`.
 */

export const THEME_OPTIONS = ["light", "dark", "system"] as const;

export type ThemeOption = (typeof THEME_OPTIONS)[number];

export const DEFAULT_THEME: ThemeOption = "system";

export function isThemeOption(value: unknown): value is ThemeOption {
  return (
    typeof value === "string" &&
    (THEME_OPTIONS as readonly string[]).includes(value)
  );
}

/**
 * Coerce whatever `next-themes` reports into a value the radio group can show.
 * It is `undefined` during the first client paint and could be any string from
 * a stale storage entry.
 */
export function normalizeTheme(value: string | undefined): ThemeOption {
  return isThemeOption(value) ? value : DEFAULT_THEME;
}
