<!-- last_verified: 2026-11-17 -->
# Feature: Settings

## Purpose
Show the tiering policy the API is actually running with, and let the user pick
a theme. The policy is server configuration, so it is read-only here.

## Used By
- UI: `/settings` page (`SettingsForm`, `PolicyCard`)
- API: `GET /tiering/policy`
- Storage: `next-themes`' own key for the theme. No server-side preferences store

## Core Functions
- `apps/web/src/components/settings/settings-form.tsx` — read-only policy card plus the theme form
- `apps/web/src/lib/settings-schema.ts` — zod schema (theme only), unit-tested in `settings-schema.test.ts`
- `apps/web/src/lib/theme-preference.ts` — `THEME_OPTIONS`, `DEFAULT_THEME`, `normalizeTheme()`
- `services/api/app/service/tiering.py` — `get_policy()`

## Canonical Files
- Pattern exemplar (selector for finite options, description hints): `apps/web/src/components/settings/settings-form.tsx`

## Inputs
- Theme: `light` | `dark` | `system` (radio group)

## Outputs
- `TieringPolicy {idle_seconds, sweep_interval_seconds, prune_enabled}`, each shown with the
  environment variable that sets it (`TIERING_IDLE_SECONDS`, `TIERING_SWEEP_INTERVAL_SECONDS`,
  `SNAPSHOT_PRUNE_ENABLED`)
- Side effect: theme applied and persisted in this browser

## Flow
- The policy loads from the API and is displayed; changing it means editing the API
  environment and restarting the API. A browser toggle that did not change what the
  background sweep does would misrepresent the system.
- Saving the theme applies it immediately; the header toggle drives the same state.

## Edge Cases
- API down -> the policy card shows its skeleton; theme still works
- Sweep interval `0` -> shown as "disabled"

## UX States (if applicable)
- Loading: skeleton in the policy card
- Error: the global health banner explains a down API or Qdrant

## Verification
- Test files: `apps/web/src/lib/settings-schema.test.ts`, `services/api/tests/test_tiering_policy.py::test_policy_reports_configuration`
- Focused verify command: `pnpm test:web`
- Default pre-PR verify command: `pnpm verify`
- Pass criteria: the schema accepts the three themes and rejects others; the policy endpoint returns its three fields

## Related Docs
- [Tiering](tiering.md)
- [README.md](../../README.md)
