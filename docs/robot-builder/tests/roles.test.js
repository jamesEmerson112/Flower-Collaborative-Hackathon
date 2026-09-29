import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import * as build from '../src/build.js';

const catalog = JSON.parse(readFileSync(new URL('../public/catalog.json', import.meta.url)));
const layout = JSON.parse(readFileSync(new URL('../src/layout.json', import.meta.url)));

test('RB2: researched categories exclude rover torsos and electronics heads', () => {
  for (const id of ['waveshare-wave-rover', 'pololu-3500']) {
    assert.deepEqual(catalog.find(p => p.id === id).roles, ['legs']);
  }
  for (const id of ['adafruit-4754', 'robotis-903-0257-000']) {
    assert.deepEqual(catalog.find(p => p.id === id).roles, ['support']);
  }
  const starter = build.createBuild(catalog);
  for (const slot of build.SLOTS) {
    assert.ok(catalog.find(p => p.id === starter.slots[slot.id]).roles.includes(slot.role), slot.id);
  }
  assert.equal(starter.slots.torso, 'sparkfun-rob-13301');
});

test('RB2: rover fills both leg slots, renders and counts as one horizontal base', () => {
  const initial = build.createBuild(catalog);
  const rover = build.setPart(initial, 'leftLeg', 'waveshare-wave-rover', catalog);
  assert.equal(rover.slots.rightLeg, 'waveshare-wave-rover');
  const summary = build.summarizeBuild(rover, catalog);
  assert.equal(summary.lines.find(p => p.id === 'waveshare-wave-rover').quantity, 1);
  assert.equal(summary.count, 5);
  const plan = build.createScenePlan(rover, catalog, layout);
  assert.equal(plan.length, 5);
  const base = plan.find(p => p.slot === 'locomotion');
  assert.deepEqual(base.slots, ['leftLeg', 'rightLeg']);
  assert.equal(base.position[0], 0);
  assert.ok(base.size[0] > base.size[1] && base.size[2] > base.size[1]);
  assert.ok(base.position[1] < plan.find(p => p.slot === 'torso').position[1]);
  assert.equal(base.rotation[2], 0, 'do not rotate it vertically like a limb');
});

test('RB2: replacing a shared base restores independent legs with accurate quantities', () => {
  const rover = build.setPart(build.createBuild(catalog), 'rightLeg', 'waveshare-wave-rover', catalog);
  const independent = build.setPart(rover, 'leftLeg', 'adafruit-3777', catalog);
  assert.equal(independent.slots.leftLeg, 'adafruit-3777');
  assert.equal(independent.slots.rightLeg, 'adafruit-3777');
  const summary = build.summarizeBuild(independent, catalog);
  assert.equal(summary.lines.find(p => p.id === 'adafruit-3777').quantity, 2);
  assert.equal(summary.count, 6);
});

test('RB2: migrate wrong legacy roles, preserve valid choices and v2 custom placements', () => {
  const legacy = { version: 1, slots: {
    torso: 'pololu-3500', head: 'adafruit-4754', leftArm: 'waveshare-21568',
    rightArm: 'servocity-2002-0180-0002', leftLeg: 'sparkfun-rob-09238', rightLeg: 'sparkfun-rob-09238',
  } };
  const migrated = build.restoreBuild(JSON.stringify(legacy), catalog);
  assert.equal(migrated.version, 2);
  assert.equal(migrated.slots.torso, 'sparkfun-rob-13301');
  assert.equal(migrated.slots.head, 'pololu-3415');
  assert.equal(migrated.slots.leftArm, 'waveshare-21568');
  const custom = build.setPart(migrated, 'head', 'adafruit-3777', catalog);
  assert.deepEqual(build.restoreBuild(build.serializeBuild(custom), catalog), custom);
});
