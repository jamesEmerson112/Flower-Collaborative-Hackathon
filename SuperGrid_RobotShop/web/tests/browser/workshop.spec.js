import { test, expect } from '@playwright/test';
import { readFile } from 'node:fs/promises';

async function ready(page) {
  await expect(page.locator('#export')).toBeEnabled({ timeout: 45000 });
  await expect(page.locator('#model-error')).toBeHidden();
}

test('mix suppliers, preserve other slots, save choices and export real geometry', async ({ page }) => {
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.goto('/');
  await ready(page);
  await expect(page.locator('#supplier-count')).toHaveText('4');
  await expect(page.locator('#total')).toHaveCount(0);
  const before = JSON.parse(await page.locator('#viewport').getAttribute('data-parts'));
  await page.locator('[data-slot="head"]').click();
  await page.locator('#all-parts').click();
  await page.locator('[data-part="niryo-ned2"]').click();
  await ready(page);
  const after = JSON.parse(await page.locator('#viewport').getAttribute('data-parts'));
  expect(after).toEqual({ ...before, head: 'niryo-ned2' });
  await page.reload();
  await ready(page);
  expect(JSON.parse(await page.locator('#viewport').getAttribute('data-parts'))).toEqual(after);
  const jsonEvent = page.waitForEvent('download');
  await page.locator('#save').click();
  const json = await jsonEvent;
  expect(JSON.parse(await readFile(await json.path(), 'utf8')).slots).toEqual(after);
  const glbEvent = page.waitForEvent('download');
  await page.locator('#export').click();
  const glb = await glbEvent;
  const data = await readFile(await glb.path());
  expect(data.toString('ascii', 0, 4)).toBe('glTF');
  expect(data.readUInt32LE(8)).toBe(data.length);
  const doc = JSON.parse(data.toString('utf8', 20, 20 + data.readUInt32LE(12)));
  expect(doc.meshes.length).toBeGreaterThan(0);
  expect(doc.nodes.filter(n => n.extras?.slot)).toHaveLength(5);
  const base = doc.nodes.filter(n => n.extras?.slot === 'locomotion');
  expect(base).toHaveLength(1);
  expect(base[0].extras.slots).toEqual(['leftLeg', 'rightLeg']);
  expect(base[0].extras.product_id).toBe('waveshare-wave-rover');
  expect(errors).toEqual([]);
});

test('all nineteen body previews load, filters recover, desktop and mobile previews fit', async ({ page }) => {
  await page.goto('/');
  await ready(page);
  await page.locator('#all-parts').click();
  await expect(page.locator('.part-card')).toHaveCount(19);
  const ids = await page.locator('.part-card').evaluateAll(cards => cards.map(c => c.dataset.part));
  for (const id of ids) {
    await page.locator(`[data-part="${id}"]`).click();
    await ready(page);
    expect(JSON.parse(await page.locator('#viewport').getAttribute('data-parts')).torso).toBe(id);
  }
  await page.locator('#search').fill('missing-wombat-part');
  await expect(page.locator('#empty')).toBeVisible();
  await page.locator('#clear-filters').click();
  await expect(page.locator('.part-card')).toHaveCount(19);
  await page.locator('#reset').click();
  await ready(page);
  await page.locator('#all-parts').click();
  await expect(page.locator('#status')).not.toHaveClass(/visible/);
  await page.screenshot({ path: 'test-results/workshop-desktop.png', fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.locator('[data-slot="rightArm"]').click();
  await page.locator('[data-part="waveshare-roarm-m3-s"]').click();
  await ready(page);
  await page.locator('#front').focus();
  await page.keyboard.press('Enter');
  await page.locator('#spread').click();
  await expect(page.locator('#spread')).toHaveAttribute('aria-pressed', 'true');
  await page.locator('#spread').click();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await expect(page.locator('#status')).not.toHaveClass(/visible/);
  await page.screenshot({ path: 'test-results/workshop-mobile.png', fullPage: true });
});

test('RB2: recommendations, shared base pose, and existing saved builds are corrected', async ({ page }) => {
  await page.goto('/');
  await ready(page);
  await expect(page.locator('[data-part="waveshare-wave-rover"]')).toHaveCount(0);
  await expect(page.locator('[data-part="reachy2-torso"]')).toBeVisible();
  await page.locator('[data-slot="head"]').click();
  await expect(page.locator('[data-part="adafruit-4754"]')).toHaveCount(0);
  await expect(page.locator('[data-part="robotis-903-0257-000"]')).toHaveCount(0);
  await expect(page.locator('[data-part="seeed-100054390"]')).toBeVisible();
  await page.locator('[data-slot="leftLeg"]').click();
  await expect(page.locator('[data-part="waveshare-wave-rover"]')).toBeVisible();
  await page.locator('#all-parts').click();
  await page.locator('[data-part="niryo-ned2"]').click();
  await ready(page);
  await expect(page.locator('#parts-count')).toHaveText('6 parts');
  await page.locator('[data-part="waveshare-wave-rover"]').click();
  await ready(page);
  await expect(page.locator('#parts-count')).toHaveText('5 parts');
  const plan = JSON.parse(await page.locator('#viewport').getAttribute('data-placements'));
  expect(plan.filter(p => p.product_id === 'waveshare-wave-rover')).toHaveLength(1);
  const base = plan.find(p => p.slot === 'locomotion');
  expect(base.position[0]).toBe(0);
  expect(base.size[0]).toBeGreaterThan(base.size[1]);
  expect(base.rotation[2]).toBe(0);
  await page.locator('[data-part="pololu-3500"]').click();
  await ready(page);
  await expect(page.locator('#status')).not.toHaveClass(/visible/);
  await page.screenshot({ path: 'test-results/romi-base.png', fullPage: true });
  await page.evaluate(() => localStorage.setItem('supergrid.robot-shop.v1', JSON.stringify({version:1,slots:{
    torso:'pololu-3500', head:'adafruit-4754', leftArm:'waveshare-21568', rightArm:'servocity-2002-0180-0002',
    leftLeg:'sparkfun-rob-09238',rightLeg:'sparkfun-rob-09238',
  }})));
  await page.reload();
  await ready(page);
  const restored = JSON.parse(await page.locator('#viewport').getAttribute('data-parts'));
  expect(restored.torso).toBe('reachy2-torso');
  expect(restored.head).toBe('reachy2-head');
  expect(restored.leftArm).toBe('niryo-ned2');
  expect(await page.evaluate(() => JSON.parse(localStorage.getItem('supergrid.robot-shop.v1')).version)).toBe(4);
});

test('a failed model keeps the previous preview and can be retried', async ({ page }) => {
  await page.goto('/');
  await ready(page);
  const before = await page.locator('#viewport').getAttribute('data-parts');
  const route = '**/models/waveshare-roarm-m3-s.glb';
  await page.route(route, request => request.abort());
  await page.locator('[data-slot="leftArm"]').click();
  await page.locator('[data-part="waveshare-roarm-m3-s"]').click();
  await expect(page.locator('#model-error')).toBeVisible();
  await expect(page.locator('#export')).toBeDisabled();
  expect(await page.locator('#viewport').getAttribute('data-parts')).toBe(before);
  await page.unroute(route);
  await page.locator('#retry').click();
  await ready(page);
  expect(JSON.parse(await page.locator('#viewport').getAttribute('data-parts')).leftArm).toBe('waveshare-roarm-m3-s');
});

test('RB4: only usable body models are shown, with no shopping or components flow', async ({page}) => {
 await page.goto('/'); await ready(page);
 await expect(page.locator('#components')).toHaveCount(0);
 await expect(page.locator('#total')).toHaveCount(0);
 await page.locator('[data-slot="leftArm"]').click();
 await expect(page.locator('.part-card')).toHaveCount(5);
 await expect(page.locator('[data-part="waveshare-21568"]')).toHaveCount(0);
 await expect(page.locator('[data-part="niryo-ned2"]')).toBeVisible();
 await page.locator('[data-slot="head"]').click();
 await expect(page.locator('.part-card')).toHaveCount(2);
 await page.locator('[data-slot="torso"]').click();
 await expect(page.locator('.part-card')).toHaveCount(9);
});
