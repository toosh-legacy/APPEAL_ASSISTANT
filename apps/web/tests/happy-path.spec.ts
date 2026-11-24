import { test, expect, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import fs from "node:fs";
import path from "node:path";

const gold = fs.readFileSync(path.join(__dirname, "../../../evals/gold/letters.jsonl"), "utf-8").split("\n")[0];
const letter = JSON.parse(gold).text as string;

async function axe(page: Page, name: string) {
  const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"]).analyze();
  const serious = results.violations.filter((v) => v.impact === "serious" || v.impact === "critical");
  expect(serious.map((v) => `${name}: ${v.id} ${v.help}`)).toEqual([]);
}

test("paste -> confirm -> letter -> export", async ({ page }) => {
  await page.goto("/");
  await axe(page, "landing");
  await page.getByRole("link", { name: "Start my appeal" }).click();
  await page.getByLabel("Paste the text of your letter").fill(letter);
  await page.getByRole("checkbox").check();
  await axe(page, "start");
  await page.getByRole("button", { name: "Continue" }).click();

  await expect(page.getByRole("heading", { name: "Check the facts" })).toBeVisible({ timeout: 30_000 });
  await axe(page, "confirm");
  await page.getByRole("button", { name: "These facts are correct" }).click();

  // Human in the loop: if the classifier is unsure, the user picks the category (F4 AC2).
  const letterHeading = page.getByRole("heading", { name: "Your appeal letter" });
  const picker = page.getByRole("button", { name: /^Medical necessity\./ });
  await expect(letterHeading.or(picker)).toBeVisible({ timeout: 120_000 });
  if (await picker.isVisible()) {
    await axe(page, "category-picker");
    await picker.click();
  }
  await expect(letterHeading).toBeVisible({ timeout: 120_000 });
  await expect(page.getByRole("heading", { name: "Your deadline" })).toBeVisible();
  await expect(page.getByText("These are California decisions")).toBeVisible();
  await axe(page, "workspace");

  // fill the placeholder, then export
  // the closing section is a Tiptap editor (one paragraph per sentence); replace its placeholder line
  const closing = page.getByRole("textbox", { name: "Closing text" });
  await expect(closing).toContainText("[ADD: your phone number or email]");
  await closing.getByText("[ADD: your phone number or email]").click({ clickCount: 3 });
  await page.keyboard.type("Phone: 555-0100");
  await expect(closing).not.toContainText("[ADD:");
  const [dl] = await Promise.all([page.waitForEvent("download"), page.getByRole("button", { name: "Download PDF" }).click()]);
  expect(dl.suggestedFilename()).toBe("appeal-letter.pdf");

  // footnote opens the exact source
  await page
    .getByRole("button", { name: /^Source 1/ })
    .first()
    .click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await page.getByRole("button", { name: "Close" }).click();
});

test("about page has attribution", async ({ page }) => {
  await page.goto("/about/data");
  await expect(page.getByText("California Department of Managed Health Care").first()).toBeVisible();
  await axe(page, "about");
});

test("insurer insights shows CMS disclaimer", async ({ page }) => {
  await page.goto("/insights/insurers");
  await expect(page.getByText("not necessarily indicative of issuer strength or plan quality")).toBeVisible({ timeout: 15_000 });
  await axe(page, "insights");
});

test("admin page renders the token form", async ({ page }) => {
  await page.goto("/admin");
  await expect(page.getByLabel("Admin token (from .env)")).toBeVisible();
  await axe(page, "admin");
});
