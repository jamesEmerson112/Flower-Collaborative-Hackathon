import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createBuild, restoreBuild, serializeBuild, setPart } from '../src/build.js';
const catalog = JSON.parse(readFileSync(new URL('../public/catalog.json', import.meta.url)));
test('RB3: arms are complete assemblies and components are separate', () => {
 const arms = catalog.filter(p => p.roles.includes('arms'));
 assert.ok(arms.length >= 3);
 assert.ok(arms.every(p => p.partType === 'robotic_arm_kit'));
 assert.ok(catalog.filter(p => p.roles.includes('torso')).length >= 3);
 assert.ok(catalog.every(p => p.catalogGroup === 'body'));
});
test('RB3: old motor arms migrate while deliberate new placements survive', () => {
 const old = createBuild(catalog); old.version = 2;
 old.slots.leftArm = 'waveshare-21568';
 const migrated = restoreBuild(JSON.stringify(old), catalog);
 assert.equal(catalog.find(p => p.id === migrated.slots.leftArm).partType, 'robotic_arm_kit');
 const custom = setPart(migrated, 'leftArm', 'reachy2-head', catalog);
 assert.deepEqual(restoreBuild(serializeBuild(custom), catalog), custom);
});
