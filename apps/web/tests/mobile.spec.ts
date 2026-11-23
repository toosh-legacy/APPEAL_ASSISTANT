import { test, expect, type Page } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";

// SPEC 21.6 mobile pass: every page at common phone widths must not scroll sideways, controls must meet
// WCAG 2.2 target size (24x24 CSS px; inline links in running text are exempt) and text must stay readable.
const WIDTHS = [320, 375, 414];
const API = process.env.API_URL ?? "http://127.0.0.1:8000";
const letter = JSON.parse(fs.readFileSync(path.join(__dirname, "../../../evals/gold/letters.jsonl"), "utf-8").split("\n")[0]).text as string;

test.skip(({ isMobile }) => !isMobile, "runs once (mobile project), with its own viewports");

async function checkLayout(page: Page, label: string) {
  const r = await page.evaluate(() => {
    const overflow = document.documentElement.scrollWidth - window.innerWidth;
    const small: string[] = [];
    for (const el of Array.from(document.querySelectorAll<HTMLElement>("a, button, input, select, textarea, [role=button], summary"))) {
      const box = el.getBoundingClientRect();
      if (box.width === 0 || box.height === 0) continue; // hidden
      const cs = getComputedStyle(el);
      if (el.classList.contains("sr-only") || cs.clipPath.includes("inset(50%)") || cs.clip.startsWith("rect(0")) continue; // visually hidden until focused (skip link)
      if (el.tagName === "A" && el.closest("p, li")) continue; // inline link exception
      if (el.tagName === "INPUT" && (el as HTMLInputElement).type === "checkbox" && el.closest("label")) continue; // label is the target
      if (box.width < 24 || box.height < 24)
        small.push(
          `${el.tagName.toLowerCase()} "${(el.textContent || el.getAttribute("aria-label") || "").trim().slice(0, 30)}" ${Math.round(box.width)}x${Math.round(box.height)}`,
        );
    }
    const tiny: string[] = [];
    for (const el of Array.from(document.querySelectorAll<HTMLElement>("p, li, label, td, th, span, a, button"))) {
      if (!el.textContent?.trim() || el.getBoundingClientRect().height === 0) continue;
      const fs = parseFloat(getComputedStyle(el).fontSize);
      if (fs < 12) tiny.push(`${el.tagName.toLowerCase()} ${fs}px "${el.textContent.trim().slice(0, 30)}"`);
    }
    return { overflow, small: small.slice(0, 10), tiny: tiny.slice(0, 10) };
  });
  expect.soft(r.overflow, `${label}: page scrolls sideways by ${r.overflow}px`).toBeLessThanOrEqual(1);
  expect.soft(r.small, `${label}: controls smaller than 24x24`).toEqual([]);
  expect.soft(r.tiny, `${label}: text smaller than 12px`).toEqual([]);
}

for (const width of WIDTHS) {
  test(`static pages fit at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 800 });
    for (const url of ["/", "/start", "/about/data", "/insights/insurers", "/admin"]) {
      await page.goto(url);
      await page.waitForLoadState("networkidle");
      await checkLayout(page, `${url} @${width}`);
    }
  });

  test(`case pages fit at ${width}px`, async ({ page, request }) => {
    await page.setViewportSize({ width, height: 800 });
    const res = await request.post(`${API}/v1/cases`, { data: { text: letter }, headers: { "Idempotency-Key": `mobile-${width}-${Date.now()}` } });
    expect(res.status()).toBe(201);
    const { id, access_token } = await res.json();
    await page.goto("/");
    await page.evaluate(([k, v]) => localStorage.setItem(k, v), [`case:${id}`, access_token]);

    await page.goto(`/cases/${id}/confirm`);
    await expect(page.getByRole("heading", { name: "Check the facts" })).toBeVisible({ timeout: 30_000 });
    await checkLayout(page, `confirm @${width}`);
    await page.getByRole("button", { name: "These facts are correct" }).click();

    const letterHeading = page.getByRole("heading", { name: "Your appeal letter" });
    const picker = page.getByRole("button", { name: /^Medical necessity\./ });
    await expect(letterHeading.or(picker)).toBeVisible({ timeout: 120_000 });
    if (await picker.isVisible()) {
      await checkLayout(page, `category picker @${width}`);
      await picker.click();
    }
    await expect(letterHeading).toBeVisible({ timeout: 120_000 });
    await checkLayout(page, `workspace @${width}`);
  });
}
