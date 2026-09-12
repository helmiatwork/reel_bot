import { test, expect } from '@playwright/test';

test.describe('Reelbot Dashboard Smoke Suite', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
  });

  test('loads dashboard overview, brand title, and topbar elements', async ({ page }) => {
    // Brand header
    const brand = page.locator('.brand');
    await expect(brand).toBeVisible();
    await expect(brand).toContainText('reelbot');

    // Topbar elements
    const searchInput = page.locator('.tb-search input');
    await expect(searchInput).toBeVisible();

    const userProfile = page.locator('.tb-user');
    await expect(userProfile).toBeVisible();
    await expect(userProfile).toContainText('Helmi');

    // Main content area
    const content = page.locator('.content');
    await expect(content).toBeVisible();
    await expect(page.locator('.content h1')).toBeVisible();
  });

  test('sidebar navigation allows switching between essential views', async ({ page }) => {
    const nav = page.locator('nav.nav');
    await expect(nav).toBeVisible();

    // Initially Dashboard should be active
    const dashboardLink = nav.locator('a', { hasText: 'Dashboard' });
    await expect(dashboardLink).toHaveClass(/active/);

    // Switch to Clipper view
    const clipperLink = nav.locator('a', { hasText: 'Clipper' });
    await expect(clipperLink).toBeVisible();
    await clipperLink.click();
    await expect(clipperLink).toHaveClass(/active/);
    await expect(dashboardLink).not.toHaveClass(/active/);

    // Switch to Snoop view
    const snoopLink = nav.locator('a', { hasText: 'Snoop' });
    await expect(snoopLink).toBeVisible();
    await snoopLink.click();
    await expect(snoopLink).toHaveClass(/active/);
    await expect(clipperLink).not.toHaveClass(/active/);

    // Return to Dashboard
    await dashboardLink.click();
    await expect(dashboardLink).toHaveClass(/active/);
  });

  test('theme toggle switches between light and dark themes', async ({ page }) => {
    const body = page.locator('body');
    const themeBtn = page.locator('.tb-icon').filter({
      has: page.locator('svg use[*|href*="moon"], svg use[*|href*="sun"]')
    });
    await expect(themeBtn).toBeVisible();

    const initialClass = await body.getAttribute('class');
    await themeBtn.click();

    if (initialClass?.includes('dark')) {
      await expect(body).toHaveClass(/light/);
      await themeBtn.click();
      await expect(body).toHaveClass(/dark/);
    } else {
      await expect(body).toHaveClass(/dark/);
      await themeBtn.click();
      await expect(body).toHaveClass(/light/);
    }
  });

  test('language toggle changes active locale', async ({ page }) => {
    const langToggle = page.locator('.lang-toggle');
    await expect(langToggle).toBeVisible();

    const idBtn = langToggle.locator('button.lang-btn', { hasText: 'ID' });
    const enBtn = langToggle.locator('button.lang-btn', { hasText: 'EN' });

    await enBtn.click();
    await expect(enBtn).toHaveClass(/active/);
    await expect(idBtn).not.toHaveClass(/active/);

    await idBtn.click();
    await expect(idBtn).toHaveClass(/active/);
    await expect(enBtn).not.toHaveClass(/active/);
  });

  test('renders responsively on desktop and mobile viewports', async ({ page }) => {
    // Desktop viewport
    await page.setViewportSize({ width: 1280, height: 800 });
    const sidebar = page.locator('.side');
    await expect(sidebar).toBeVisible();
    const sideBox = await sidebar.boundingBox();
    expect(sideBox?.width).toBeGreaterThan(200);

    const main = page.locator('.main');
    await expect(main).toBeVisible();

    // Mobile viewport
    await page.setViewportSize({ width: 375, height: 667 });
    await expect(page.locator('.brand')).toBeVisible();
    await expect(page.locator('.content')).toBeVisible();
  });
});
