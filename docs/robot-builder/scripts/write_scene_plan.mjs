import { readFile, writeFile, mkdir } from 'node:fs/promises';
import { createBuild, createScenePlan } from '../src/build.js';
const root = new URL('../', import.meta.url);
const catalog = JSON.parse(await readFile(new URL('public/catalog.json', root)));
const layout = JSON.parse(await readFile(new URL('src/layout.json', root)));
await mkdir(new URL('blender/intermediate/', root), { recursive: true });
await writeFile(new URL('blender/intermediate/starter-plan.json', root), JSON.stringify(createScenePlan(createBuild(catalog), catalog, layout), null, 2));
console.log('Prepared shared browser/Blender placement plan');
