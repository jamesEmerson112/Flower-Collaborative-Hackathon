import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync,existsSync} from 'node:fs';
import {createBuild,summarizeBuild} from '../src/build.js';
const root=new URL('../public/',import.meta.url);
const catalog=JSON.parse(readFileSync(new URL('catalog.json',root)));
test('RB4: every visible choice is a prepared physical body section',()=>{
 assert.ok(catalog.every(p=>p.catalogGroup==='body'));
 assert.ok(catalog.every(p=>p.modelKind!=='approximate_preview'));
 for(const p of catalog){assert.ok(existsSync(new URL(p.model,root)),p.id);assert.ok(existsSync(new URL(p.thumbnail,root)),p.id)}
 assert.ok(catalog.filter(p=>p.roles.includes('arms')).length>=4);
 assert.ok(catalog.some(p=>p.id==='reachy2-torso'));
});

test('RB4: unknown section prices are never represented as free',()=>{assert.equal(summarizeBuild(createBuild(catalog),catalog).total,null)});

test('RB5: five additional official humanoid torsos are ready',()=>{
 for(const id of ['robotis-op3-torso','berkeley-lite-torso','unitree-g1-torso','unitree-h1-torso','unitree-h2-torso']){
  const p=catalog.find(p=>p.id===id);
  assert.ok(p,id); assert.deepEqual(p.roles,['torso']);
  assert.equal(p.modelKind,'robot_section'); assert.equal(p.defaultSlots.length,0);
  assert.ok(existsSync(new URL(p.model,root)),id);
 }
});
