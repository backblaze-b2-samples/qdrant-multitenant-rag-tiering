import { test, expect } from "@playwright/test";

/**
 * Smoke journey through the primary feature: seed, query warm, park, and see
 * the next query restore the tenant from B2. Needs the live stack (Qdrant +
 * API with B2 credentials + web), e.g. `docker compose up qdrant` and `pnpm dev`.
 *
 * It uses the seeded `acme-legal` tenant; seeding skips tenants that exist, so
 * re-running is safe.
 */
test.describe("Tenant tiering", () => {
  test.setTimeout(240_000);

  test("seed, query, park, and restore on the next query", async ({ page }) => {
    await page.goto("/tenants");
    await page.getByRole("button", { name: "Seed demo tenants" }).click();
    await expect(page.getByRole("link", { name: "Acme Legal" })).toBeVisible({ timeout: 180_000 });

    await page.getByRole("link", { name: "Acme Legal" }).click();
    await expect(page).toHaveURL(/\/tenants\/acme-legal$/);

    // Make sure it is hot before the warm query (a previous run may have parked it).
    const restoreNow = page.getByRole("button", { name: "Restore now" });
    if (await restoreNow.isEnabled()) {
      await restoreNow.click();
      await expect(page.locator('[data-state="hot"]').first()).toBeVisible({ timeout: 60_000 });
    }

    const question = page.getByLabel("Question");
    await question.fill("How much notice is needed to terminate a supplier contract?");
    await page.getByRole("button", { name: "Search" }).click();
    await expect(page.getByTestId("query-latency")).toBeVisible({ timeout: 60_000 });
    await expect(page.getByText("supplier-contracts.md").first()).toBeVisible();

    await page.getByRole("button", { name: "Park now" }).click();
    await expect(page.locator('[data-state="parked"]').first()).toBeVisible({ timeout: 60_000 });

    await page.getByRole("button", { name: "Search" }).click();
    await expect(page.getByTestId("restore-notice")).toBeVisible({ timeout: 120_000 });
    await expect(page.locator('[data-state="hot"]').first()).toBeVisible({ timeout: 30_000 });
  });

  test("navigation reaches every screen", async ({ page }) => {
    for (const path of ["/", "/tenants", "/reports", "/library", "/files", "/settings"]) {
      await page.goto(path);
      await expect(page.locator("h1").first()).toBeVisible();
    }
  });
});
