import { test, expect } from "@playwright/test";
import { registerAndLogin, collectConsoleErrors } from "./helpers";

// Covers PART 11's "investigator must understand WHO/WHAT/WHERE/WHEN/
// SOURCE/CATEGORY/WHY" requirement, plus export buttons and the relationship
// graph — the two other pieces of an actor profile a real investigator
// depends on. Assumes at least one actor exists in the DB (true for the
// dev stack after any ingestion script has run); skips gracefully if not.

test("actor profile: attribution, threat categories, graph, and exports all render", async ({ page }) => {
  const console_ = collectConsoleErrors(page);
  await registerAndLogin(page);

  await page.getByRole("button", { name: "Threat Actors", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Threat Actors" })).toBeVisible();

  // Wait for the list to actually resolve (either real rows or the honest
  // empty state) before deciding whether to skip — checking count()
  // immediately after the click races the initial data fetch.
  const firstRow = page.locator(".actor-row").first();
  await Promise.race([
    firstRow.waitFor({ state: "visible", timeout: 10_000 }).catch(() => undefined),
    page.getByText("No actors found").waitFor({ state: "visible", timeout: 10_000 }).catch(() => undefined),
  ]);
  const hasActors = (await firstRow.count()) > 0;
  test.skip(!hasActors, "No actors in the current DB — run an ingestion script first.");

  await firstRow.click();

  // WHO / attribution confidence.
  await expect(page.getByText("Why this attribution?")).toBeVisible();

  // Relationship graph (WHERE/WHO's connections).
  await expect(page.getByText("Relationship graph")).toBeVisible();

  // Observed Threat Categories — WHAT/CATEGORY, expandable to WHY/WHEN/SOURCE.
  const categorySection = page.getByText("Observed Threat Categories");
  await expect(categorySection).toBeVisible();

  const firstCategory = page.locator(".threat-category-row").first();
  if ((await firstCategory.count()) > 0) {
    await firstCategory.click();
    // Expanding a category must reveal per-item evidence: source, persona,
    // activity text, classification reason (WHY), and observed date (WHEN).
    await expect(page.getByRole("columnheader", { name: "Why classified" })).toBeVisible();
    await expect(page.getByRole("columnheader", { name: "Observed" })).toBeVisible();
  } else {
    // Honest empty state — never a fabricated populated table.
    await expect(page.getByText("No classifiable activity found.")).toBeVisible();
  }

  // Export buttons exist and are actionable (real download, not decorative).
  const exportButton = page.getByRole("button", { name: /Export CSV/i });
  await expect(exportButton).toBeVisible();
  const [download] = await Promise.all([
    page.waitForEvent("download", { timeout: 10_000 }),
    exportButton.click(),
  ]);
  expect(download.suggestedFilename()).toMatch(/\.csv$/);

  console_.assertNoErrors();
});
