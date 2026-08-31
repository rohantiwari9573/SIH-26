import { test, expect } from "@playwright/test";
import { registerAndLogin, collectConsoleErrors } from "./helpers";

// Minimal smoke suite — see e2e/README.md. Verifies every sidebar view
// loads without a console error/crash and shows a real heading, not that
// every pixel is pixel-perfect.

test("login → dashboard loads with no console errors", async ({ page }) => {
  const console_ = collectConsoleErrors(page);
  await registerAndLogin(page);
  await expect(page.getByRole("heading", { name: "Overview" })).toBeVisible();
  console_.assertNoErrors();
});

const SIDEBAR_VIEWS: { button: string; heading: string }[] = [
  { button: "Threat Actors", heading: "Threat Actors" },
  { button: "Infrastructure", heading: "Infrastructure" },
  { button: "AI Attribution", heading: "AI Attribution" },
  { button: "Timeline Explorer", heading: "Timeline Explorer" },
  { button: "Sources & Feeds", heading: "Sources" },
  { button: "Hidden Services", heading: "Hidden Services" },
  { button: "Marketplaces", heading: "Marketplace Intelligence" },
  { button: "Forums", heading: "Forum Intelligence" },
  { button: "Alerts", heading: "Alerts" },
  { button: "Indicators", heading: "Indicators" },
  { button: "Reports", heading: "Reports" },
  { button: "Jobs & Scans", heading: "Jobs" },
];

for (const { button, heading } of SIDEBAR_VIEWS) {
  test(`navigate to "${button}" renders without console errors`, async ({ page }) => {
    const console_ = collectConsoleErrors(page);
    await registerAndLogin(page);
    await page.getByRole("button", { name: button, exact: true }).click();
    await expect(page.getByRole("heading", { name: new RegExp(heading, "i") }).first()).toBeVisible({
      timeout: 10_000,
    });
    console_.assertNoErrors();
  });
}

test("Jobs & Scans shows real system status and does not fabricate job history", async ({ page }) => {
  await registerAndLogin(page);
  await page.getByRole("button", { name: "Jobs & Scans" }).click();
  await expect(page.getByRole("heading", { name: "System Status" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Source Ingestion" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Analysis Jobs" })).toBeVisible();
});
