import test from 'node:test';
import assert from 'node:assert/strict';
import { createBuild, setPart, summarizeBuild, serializeBuild, restoreBuild } from '../src/build.js';

const catalog = [
  { id: 'body-a', name: 'Chassis', supplier: 'Pololu', price: 39.95, defaultSlots: ['torso'] },
  { id: 'sensor-b', name: 'Sensor', supplier: 'Adafruit', price: 29.50, defaultSlots: ['head'] },
  { id: 'servo-c', name: 'Servo', supplier: 'ROBOTIS', price: 25.90, defaultSlots: ['leftArm', 'rightArm'] },
  { id: 'motor-d', name: 'Motor', supplier: 'SparkFun', price: 26.95, defaultSlots: ['leftLeg', 'rightLeg'] },
  { id: 'servo-e', name: 'Alternative', supplier: 'ServoCity', price: 18.25 },
];

test('R1: starter robot fills six slots using multiple suppliers', () => {
  const build = createBuild(catalog);
  assert.equal(Object.keys(build.slots).length, 6);
  assert.equal(summarizeBuild(build, catalog).suppliers.length, 4);
});

test('R2: cross-supplier replacement changes only the chosen slot, without fit restrictions', () => {
  const initial = createBuild(catalog);
  const result = setPart(initial, 'leftArm', 'servo-e', catalog);
  assert.equal(result.slots.leftArm, 'servo-e');
  assert.equal(result.slots.rightArm, 'servo-c');
  assert.equal(initial.slots.leftArm, 'servo-c');
  assert.deepEqual(result.slots, { ...initial.slots, leftArm: 'servo-e' });
  assert.equal(setPart(initial, 'head', 'motor-d', catalog).slots.head, 'motor-d');
});

test('R3: repeated parts are counted once with correct quantity and cents-based total', () => {
  const summary = summarizeBuild(createBuild(catalog), catalog);
  assert.equal(summary.lines.length, 4);
  assert.equal(summary.lines.find(line => line.id === 'servo-c').quantity, 2);
  assert.equal(summary.total, 175.15);
  assert.equal(summary.count, 6);
});

test('R4/R5: serialized choices survive reload; bad saved state safely resets', () => {
  const changed = setPart(createBuild(catalog), 'head', 'servo-e', catalog);
  assert.deepEqual(restoreBuild(serializeBuild(changed), catalog), changed);
  for (const value of ['broken-json', 'null', '{"version":99}', '{"version":1,"slots":{"head":"missing"}}']) {
    assert.deepEqual(restoreBuild(value, catalog), createBuild(catalog));
  }
});

test('R4: invalid IDs cannot change a build', () => {
  const initial = createBuild(catalog);
  assert.throws(() => setPart(initial, 'tail', 'servo-e', catalog), /slot/i);
  assert.throws(() => setPart(initial, 'head', 'missing', catalog), /part/i);
  assert.equal(initial.slots.head, 'sensor-b');
});
