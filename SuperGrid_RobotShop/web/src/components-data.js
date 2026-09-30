// Pure helpers for the components tray and the SuperGrid request (contract C1).
// No DOM, CSS or import.meta.env here, so node --test can import this module.
import { summarizeBuild } from './build.js';

export const MAX_COMPONENT_QTY = 99;

const PART_TYPE_LABELS = {
  motor_driver: 'Motor drivers', dc_gearmotor: 'DC gearmotors', stepper_motor: 'Stepper motors',
  hub_motor: 'Hub motors', positional_servo: 'Hobby servos', smart_servo: 'Smart servos',
  actuator_kit: 'Actuator kits', distance_sensor: 'Distance sensors', lidar: 'LiDAR',
  reflectance_sensor: 'Reflectance sensors', imu: 'IMUs', microcontroller: 'Microcontrollers',
  robot_controller: 'Robot controllers', single_board_computer: 'Single-board computers',
  interface_adapter: 'Interface adapters', battery: 'Batteries', battery_holder: 'Battery holders',
  power_module: 'Power modules', power_adapter: 'Power adapters', voltage_regulator: 'Voltage regulators',
  wheel: 'Wheels', caster: 'Casters', mobile_base: 'Mobile bases', chassis_frame: 'Chassis frames',
  robotic_arm_kit: 'Robotic arm kits', body_shell: 'Body shells', head_shell: 'Head shells',
  robot_kit: 'Complete robot kits',
};

// Display order of groups: the electronics people add most often come first.
const GROUP_ORDER = ['motor_driver', 'robot_controller', 'microcontroller', 'single_board_computer',
  'distance_sensor', 'lidar', 'imu', 'reflectance_sensor', 'positional_servo', 'smart_servo',
  'dc_gearmotor', 'stepper_motor', 'hub_motor', 'actuator_kit', 'battery', 'battery_holder',
  'power_module', 'voltage_regulator', 'power_adapter', 'interface_adapter', 'wheel', 'caster',
  'mobile_base', 'chassis_frame', 'robotic_arm_kit', 'body_shell', 'head_shell', 'robot_kit'];

export function partTypeLabel(type) {
  if (PART_TYPE_LABELS[type]) return PART_TYPE_LABELS[type];
  const words = String(type || 'other').replace(/_/g, ' ');
  return words.charAt(0).toUpperCase() + words.slice(1);
}

/** Singular label for one row ("Motor driver"), derived from the group label. */
export function partTypeSingular(type) {
  const label = partTypeLabel(type);
  if (label === 'LiDAR') return label;
  if (label.endsWith('ies')) return label.slice(0, -3) + 'y';
  return label.endsWith('s') ? label.slice(0, -1) : label;
}

export function componentMatches(component, query) {
  const q = String(query || '').trim().toLowerCase();
  if (!q) return true;
  const haystack = `${component.name} ${component.store_name} ${component.store_id} ${component.part_type} ${partTypeLabel(component.part_type)}`.toLowerCase();
  return q.split(/\s+/).every(word => haystack.includes(word));
}

/** Filter by query, then group by part_type: [{type, label, items}] in a stable, readable order. */
export function groupComponents(components, query = '') {
  const groups = new Map();
  for (const component of components) {
    if (!componentMatches(component, query)) continue;
    if (!groups.has(component.part_type)) groups.set(component.part_type, []);
    groups.get(component.part_type).push(component);
  }
  const rank = type => { const i = GROUP_ORDER.indexOf(type); return i === -1 ? GROUP_ORDER.length : i; };
  return [...groups.entries()]
    .sort(([a], [b]) => rank(a) - rank(b) || partTypeLabel(a).localeCompare(partTypeLabel(b)))
    .map(([type, items]) => ({ type, label: partTypeLabel(type), items }));
}

function isPlainObject(value) {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}

/**
 * Clean a {id: qty} map: unknown ids and non-positive / non-integer quantities are dropped,
 * quantities above 99 are clamped. `knownIds` is a Set; without it no id is dropped for being unknown.
 */
export function sanitizeComponentQty(value, knownIds) {
  const clean = {};
  if (!isPlainObject(value)) return clean;
  for (const [id, qty] of Object.entries(value)) {
    if (knownIds && !knownIds.has(id)) continue;
    if (!Number.isInteger(qty) || qty <= 0) continue;
    clean[id] = Math.min(qty, MAX_COMPONENT_QTY);
  }
  return clean;
}

/** Parse the stored JSON ({version:1, components:{id: qty}}); anything malformed gives {}. */
export function parseStoredComponents(text, knownIds) {
  try {
    const parsed = JSON.parse(text);
    return sanitizeComponentQty(isPlainObject(parsed) ? parsed.components : null, knownIds);
  } catch {
    return {};
  }
}

export function serializeComponents(componentQty) {
  return JSON.stringify({ version: 1, components: componentQty });
}

/** Return a new map with `id` set to `qty` (clamped to 1..99); qty <= 0 removes it. */
export function setComponentQty(componentQty, id, qty) {
  const next = { ...componentQty };
  const n = Math.floor(Number(qty));
  if (!Number.isFinite(n) || n <= 0) delete next[id];
  else next[id] = Math.min(n, MAX_COMPONENT_QTY);
  return next;
}

export function componentTotal(componentQty) {
  return Object.values(componentQty).reduce((sum, qty) => sum + qty, 0);
}

/**
 * Contract C1 items: the body parts (shared base counted once) plus the selected components,
 * as [{product_id, qty, name, store_id}], duplicate product_ids merged by summing qty.
 * Component ids missing from `componentsList` are skipped (the loader already drops them).
 */
export function requestItems(build, catalog, componentQty = {}, componentsList = []) {
  const items = new Map();
  const add = (product_id, qty, name, store_id) => {
    if (items.has(product_id)) items.get(product_id).qty += qty;
    else items.set(product_id, { product_id, qty, name, store_id });
  };
  for (const line of summarizeBuild(build, catalog).lines) add(line.id, line.quantity, line.name, line.storeId ?? null);
  const byId = new Map(componentsList.map(component => [component.id, component]));
  for (const [id, qty] of Object.entries(componentQty || {})) {
    const component = byId.get(id);
    if (!component || !Number.isInteger(qty) || qty <= 0) continue;
    add(id, qty, component.name, component.store_id);
  }
  return [...items.values()];
}

// One sensible pick per store, so "Add starter electronics" reaches every store node.
// Each entry is an ordered part_type preference; the store's first component is the fallback.
const STARTER_PREFERENCES = {
  adafruit: ['battery', 'distance_sensor'],
  sparkfun: ['microcontroller', 'robot_controller'],
  dfrobot: ['motor_driver'],
  robotis: ['distance_sensor', 'imu'],
  pololu: ['voltage_regulator', 'motor_driver'],
  servocity: ['positional_servo'],
  seeed: ['imu', 'distance_sensor'],
  waveshare: ['motor_driver', 'robot_controller'],
};

/**
 * Ids to add (qty 1 each): one per store in `componentsList` that has no selected component yet.
 * Idempotent: once every store has a pick, it returns [].
 */
export function starterPicks(componentsList, componentQty = {}) {
  const covered = new Set(componentsList.filter(c => componentQty[c.id] > 0).map(c => c.store_id));
  const stores = [...new Set(componentsList.map(c => c.store_id))];
  const picks = [];
  for (const store of stores) {
    if (covered.has(store)) continue;
    const own = componentsList.filter(c => c.store_id === store);
    const preferred = (STARTER_PREFERENCES[store] || []).map(type => own.find(c => c.part_type === type)).find(Boolean);
    picks.push((preferred || own[0]).id);
  }
  return picks;
}
