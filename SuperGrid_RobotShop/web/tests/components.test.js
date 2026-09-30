import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createBuild, setPart } from '../src/build.js';
import {
  componentMatches, groupComponents, parseStoredComponents, partTypeLabel, partTypeSingular,
  requestItems, sanitizeComponentQty, serializeComponents, setComponentQty, starterPicks,
} from '../src/components-data.js';

const root = new URL('../public/', import.meta.url);
const catalog = JSON.parse(readFileSync(new URL('catalog.json', root)));
const components = JSON.parse(readFileSync(new URL('components.json', root)));
const knownIds = new Set(components.map(c => c.id));

test('SG1: shop data carries no catalogue prices and components exclude body parts', () => {
  const hasPriceKey = value => JSON.stringify(value).match(/"(price|currency)":/);
  assert.equal(hasPriceKey(catalog), null);
  assert.equal(hasPriceKey(components), null);
  assert.equal(components.length, 93);
  assert.equal(knownIds.size, components.length, 'component ids are unique');
  const catalogIds = new Set(catalog.map(p => p.id));
  assert.ok(components.every(c => !catalogIds.has(c.id)));
  for (const c of components) {
    assert.deepEqual(Object.keys(c).sort(), ['id', 'name', 'part_type', 'primary_role', 'store_id', 'store_name', 'summary']);
  }
  assert.equal(new Set(components.map(c => c.store_id)).size, 8);
  assert.ok(catalog.every(p => typeof p.storeId === 'string' && p.storeId));
});

test('SG2: stored selections drop unknown ids and bad quantities, and clamp to 99', () => {
  const stored = serializeComponents({ 'adafruit-3777': 2, 'pololu-2130': 250, 'ghost-part': 1,
    'sparkfun-dev-15123': 0, 'dfrobot-dri0044': -3, 'robotis-902-0183-000': 1.5, 'seeed-101020585': '2' });
  assert.deepEqual(parseStoredComponents(stored, knownIds), { 'adafruit-3777': 2, 'pololu-2130': 99 });
  for (const bad of [null, '', 'broken-json', 'null', '[]', '{"components":[1,2]}', '{"components":"x"}']) {
    assert.deepEqual(parseStoredComponents(bad, knownIds), {}, String(bad));
  }
  assert.deepEqual(sanitizeComponentQty({ 'ghost-part': 3 }), { 'ghost-part': 3 }, 'no id list means no id filter');
  assert.deepEqual(sanitizeComponentQty(['adafruit-3777'], knownIds), {});
});

test('SG2: setComponentQty adds, clamps and removes without mutating', () => {
  const start = { 'adafruit-3777': 1 };
  const more = setComponentQty(start, 'adafruit-3777', 3);
  assert.deepEqual(more, { 'adafruit-3777': 3 });
  assert.deepEqual(start, { 'adafruit-3777': 1 });
  assert.deepEqual(setComponentQty(more, 'pololu-2130', 500), { 'adafruit-3777': 3, 'pololu-2130': 99 });
  assert.deepEqual(setComponentQty(more, 'adafruit-3777', 0), {});
  assert.deepEqual(setComponentQty(more, 'adafruit-3777', -1), {});
});

test('SG3: requestItems counts a shared base once and adds store_id (contract C1)', () => {
  const rover = setPart(createBuild(catalog), 'leftLeg', 'waveshare-wave-rover', catalog);
  const items = requestItems(rover, catalog, {}, components);
  const base = items.filter(item => item.product_id === 'waveshare-wave-rover');
  assert.equal(base.length, 1);
  assert.equal(base[0].qty, 1);
  assert.equal(base[0].store_id, 'waveshare');
  assert.equal(base[0].name, catalog.find(p => p.id === 'waveshare-wave-rover').name);
  assert.equal(items.reduce((sum, item) => sum + item.qty, 0), 5, 'five body entries with the shared base');
  for (const item of items) assert.deepEqual(Object.keys(item), ['product_id', 'qty', 'name', 'store_id']);
});

test('SG3: requestItems appends components, merges duplicate ids and skips unknown ones', () => {
  const build = setPart(createBuild(catalog), 'leftArm', 'waveshare-roarm-m2-s', catalog);
  const fakeList = [...components, { id: 'waveshare-roarm-m2-s', name: 'RoArm duplicate', store_id: 'waveshare', store_name: 'Waveshare', part_type: 'robotic_arm_kit' }];
  const items = requestItems(build, catalog, { 'adafruit-3777': 2, 'waveshare-roarm-m2-s': 3, 'ghost-part': 1 }, fakeList);
  const arm = items.filter(item => item.product_id === 'waveshare-roarm-m2-s');
  assert.equal(arm.length, 1);
  assert.equal(arm[0].qty, 4, 'one body arm plus three from the tray');
  assert.equal(arm[0].name, catalog.find(p => p.id === 'waveshare-roarm-m2-s').name, 'the body line names the merged item');
  const motor = items.find(item => item.product_id === 'adafruit-3777');
  assert.deepEqual(motor, { product_id: 'adafruit-3777', qty: 2, name: components.find(c => c.id === 'adafruit-3777').name, store_id: 'adafruit' });
  assert.equal(items.some(item => item.product_id === 'ghost-part'), false);
  assert.equal(new Set(items.map(item => item.product_id)).size, items.length);
});

test('SG3: two identical arms become one line with qty 2', () => {
  let build = setPart(createBuild(catalog), 'leftArm', 'seeed-100046482', catalog);
  build = setPart(build, 'rightArm', 'seeed-100046482', catalog);
  const arm = requestItems(build, catalog, {}, components).filter(item => item.product_id === 'seeed-100046482');
  assert.equal(arm.length, 1);
  assert.equal(arm[0].qty, 2);
});

test('SG4: tray groups by readable part type and searches name, store and type', () => {
  const all = groupComponents(components);
  assert.equal(all.reduce((sum, group) => sum + group.items.length, 0), components.length);
  assert.equal(all[0].type, 'motor_driver');
  assert.equal(all[0].label, 'Motor drivers');
  assert.ok(all.every(group => group.items.every(c => c.part_type === group.type)));
  assert.equal(partTypeLabel('imu'), 'IMUs');
  assert.equal(partTypeSingular('battery'), 'Battery');
  assert.equal(partTypeSingular('distance_sensor'), 'Distance sensor');
  assert.equal(partTypeLabel('flux_capacitor'), 'Flux capacitor');
  const drivers = groupComponents(components, 'pololu driver');
  assert.ok(drivers.length >= 1 && drivers.every(g => g.items.every(c => c.store_id === 'pololu' && c.part_type === 'motor_driver')));
  assert.ok(groupComponents(components, 'Adafruit Industries').every(g => g.items.every(c => c.store_id === 'adafruit')));
  assert.ok(groupComponents(components, 'lidar').some(g => g.type === 'lidar'));
  assert.deepEqual(groupComponents(components, 'no-such-thing-xyz'), []);
  assert.ok(componentMatches(components[0], ''));
});

test('SG5: starter electronics reach every store once and are idempotent', () => {
  const picks = starterPicks(components, {});
  assert.equal(picks.length, 8);
  const stores = picks.map(id => components.find(c => c.id === id)?.store_id);
  assert.equal(new Set(stores).size, 8);
  assert.ok(picks.every(id => knownIds.has(id)));
  let qty = {};
  for (const id of picks) qty = setComponentQty(qty, id, 1);
  assert.deepEqual(starterPicks(components, qty), []);
  const partial = starterPicks(components, { 'adafruit-3777': 1 });
  assert.equal(partial.length, 7);
  assert.ok(!partial.some(id => id.startsWith('adafruit-')));
});
