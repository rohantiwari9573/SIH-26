import { Page, expect } from "@playwright/test";

/** Registers a fresh throwaway account and logs in — every test run gets
 * its own isolated user, no shared/committed test credentials. */
export async function registerAndLogin(page: Page): Promise<void> {
  const email = `pw_smoke_${Date.now()}_${Math.floor(Math.random() * 1e6)}@example.com`;
  const password = "PlaywrightSmoke123!";

  await page.goto("/");
  await page.getByRole("button", { name: "Register" }).click();
  await page.getByLabel("Email", { exact: true }).fill(email);
  await page.getByLabel("Password", { exact: true }).fill(password);
  await page.getByRole("button", { name: "Register & log in" }).click();

  // Successful login lands on the Dashboard (sidebar becomes visible).
  await expect(page.getByRole("button", { name: "Dashboard" })).toBeVisible({ timeout: 15_000 });
}

/** Collects console errors during a test; call assertNoErrors() at the end.
 * Ignores none by default — a real console.error during a smoke pass is a
 * real signal, not noise, on this small a codebase. */
export function collectConsoleErrors(page: Page): { assertNoErrors: () => void } {
  const errors: string[] = [];
  page.on("console", (msg) => {
    if (msg.type() === "error") errors.push(msg.text());
  });
  page.on("pageerror", (err) => errors.push(err.message));
  return {
    assertNoErrors: () => {
      if (errors.length > 0) {
        throw new Error(`Console errors during test:\n${errors.join("\n")}`);
      }
    },
  };
}
