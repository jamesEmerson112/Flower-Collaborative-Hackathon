export const SLOTS = [
  { id: 'torso', label: 'Torso', role: 'torso' },
  { id: 'head', label: 'Head', role: 'head' },
  { id: 'leftArm', label: 'Left arm', role: 'arms' },
  { id: 'rightArm', label: 'Right arm', role: 'arms' },
  { id: 'leftLeg', label: 'Left leg', role: 'legs' },
  { id: 'rightLeg', label: 'Right leg', role: 'legs' },
];

export function createBuild(catalog) {
  const slots = {};
  for (const slot of SLOTS) {
    const part = catalog.find(p => p.defaultSlots?.includes(slot.id));
    if (!part) throw new Error(`No default part for slot ${slot.id}`);
    slots[slot.id] = part.id;
  }
  return { version: 4, slots };
}

export function isMobileBase(part) { return part?.partType === 'mobile_base'; }

function independentLeg(catalog) {
  return catalog.find(p => p.id === 'adafruit-3777') || catalog.find(p => p.roles?.includes('legs') && !isMobileBase(p));
}

export function setPart(build, slot, partId, catalog) {
  if (!SLOTS.some(s => s.id === slot)) throw new Error('Unknown robot slot');
  if (!catalog.some(p => p.id === partId)) throw new Error('Unknown catalog part');
  const slots = { ...build.slots, [slot]: partId };
  if (slot === 'leftLeg' || slot === 'rightLeg') {
    const other = slot === 'leftLeg' ? 'rightLeg' : 'leftLeg';
    if (isMobileBase(catalog.find(p => p.id === partId))) slots[other] = partId;
    else if (isMobileBase(catalog.find(p => p.id === slots[other]))) slots[other] = independentLeg(catalog)?.id || partId;
  }
  return { version: 4, slots };
}

export function buildParts(build, catalog) {
  const base = catalog.find(p => p.id === build.slots.leftLeg);
  const shared = isMobileBase(base) && build.slots.rightLeg === base.id;
  return SLOTS.flatMap(slot => {
    if (shared && slot.id === 'rightLeg') return [];
    return [{ slot: shared && slot.id === 'leftLeg' ? 'locomotion' : slot.id,
      slots: shared && slot.id === 'leftLeg' ? ['leftLeg', 'rightLeg'] : [slot.id],
      part: catalog.find(p => p.id === build.slots[slot.id]) }];
  });
}

export function createScenePlan(build, catalog, layout) {
  const parts = buildParts(build, catalog);
  const hasBase = parts.some(p => p.slot === 'locomotion');
  return parts.map(entry => {
    const pose = layout[entry.slot];
    const position = pose.position.map((v,i) => v + (entry.part.positionOffset?.[i] || 0));
    if (hasBase && entry.slot !== 'locomotion') position[1] -= .22;
    if (entry.part.partType === 'robotic_arm_kit' && ['leftArm','rightArm'].includes(entry.slot)) position[0] *= .95;
    return { ...entry, position, size: entry.part.slotSize || pose.size,
      rotation: entry.slot === 'locomotion' ? (entry.part.baseRotation || [-Math.PI / 2, 0, 0]) : (entry.part.slotRotations?.[entry.slot] || [0, 0, pose.limb ? Math.PI / 2 : 0]) };
  });
}

export function summarizeBuild(build, catalog) {
  const lines = new Map();
  const parts = buildParts(build, catalog);
  for (const { slot, part } of parts) {
    if (!part) throw new Error(`Missing part for ${slot}`);
    if (lines.has(part.id)) lines.get(part.id).quantity += 1;
    else lines.set(part.id, { ...part, quantity: 1 });
  }
  const result = [...lines.values()].map(line => ({
    ...line,
    subtotal: Number.isFinite(line.price) ? Math.round(line.price * 100) * line.quantity / 100 : null,
  }));
  return {
    lines: result,
    count: parts.length,
    suppliers: [...new Set(result.map(line => line.supplier))],
    total: result.some(line => line.subtotal === null) ? null : result.reduce((sum, line) => sum + Math.round(line.subtotal * 100), 0) / 100,
  };
}

export function serializeBuild(build) {
  return JSON.stringify({ version: 4, slots: build.slots }, null, 2);
}

export function restoreBuild(value, catalog) {
  try {
    const parsed = JSON.parse(value);
    if (![1, 2, 3, 4].includes(parsed?.version) || !parsed.slots || Array.isArray(parsed.slots)) throw new Error();
    const slots = {};
    const defaults = createBuild(catalog);
    for (const { id, role } of SLOTS) {
      const partId = parsed.slots[id];
      const part = catalog.find(p => p.id === partId);
      if (!part) throw new Error();
      slots[id] = parsed.version < 3 && part.roles && !part.roles.includes(role) ? defaults.slots[id] : partId;
    }
    // A shared base cannot occupy only half of the locomotion area.
    const mobile = ['leftLeg', 'rightLeg'].find(id => isMobileBase(catalog.find(p => p.id === slots[id])));
    if (mobile) slots.leftLeg = slots.rightLeg = slots[mobile];
    return { version: 4, slots };
  } catch {
    return createBuild(catalog);
  }
}
