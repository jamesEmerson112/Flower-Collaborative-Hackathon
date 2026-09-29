/** Tessellate supplier STEP assemblies with OpenCascade, retaining face colors. */
import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import occtImport from 'occt-import-js';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const cad = path.resolve(root, '../robot-parts-stores/cad');
const outputDir = path.join(root, 'blender/intermediate');
await fs.mkdir(outputDir, { recursive: true });
const occt = await occtImport();
const parts = JSON.parse(await fs.readFile(path.join(root, 'public/catalog.json'), 'utf8'));
for (const part of parts) {
  if (!/\.ste?p$/i.test(part.source)) continue;
  const source = path.join(cad, part.source);
  const output = path.join(outputDir, part.id + '.json');
  const existing = await fs.stat(output).catch(() => null);
  if (existing && existing.mtimeMs > (await fs.stat(source)).mtimeMs) continue;
  console.log('Converting', part.id);
  const result = occt.ReadStepFile(await fs.readFile(source), {
    linearUnit: 'millimeter', linearDeflectionType: 'absolute_value',
    linearDeflection: .12, angularDeflection: .25,
  });
  if (!result.success || !result.meshes.length) throw new Error(`STEP import failed: ${part.id}`);
  await fs.writeFile(output, JSON.stringify(result));
  console.log('Converted', part.id, result.meshes.length, 'meshes');
}
