import './style.css';
import { SLOTS, createBuild, setPart, summarizeBuild, serializeBuild, restoreBuild, isMobileBase } from './build.js';
import { createWorkshop } from './scene.js';

const $ = id => document.getElementById(id);
const STORAGE_KEY = 'flower.robot-workshop.v1';
const escape = value => String(value).replace(/[&<>"']/g, character => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[character]));
let toastTimer;
function notify(message) {
  $('status').textContent = message;
  $('status').classList.add('visible');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => $('status').classList.remove('visible'), 3500);
}
function download(data, name, type) {
  const url = URL.createObjectURL(new Blob([data], { type }));
  const link = document.createElement('a');
  link.href = url; link.download = name; link.click();
  setTimeout(() => URL.revokeObjectURL(url), 10000);
}

async function start() {
  const response = await fetch(import.meta.env.BASE_URL + 'catalog.json');
  if (!response.ok) throw new Error('The parts catalog could not load.');
  const catalog = await response.json();
  let saved;
  try { saved = localStorage.getItem(STORAGE_KEY); } catch { /* The builder works without browser storage. */ }
  let build = restoreBuild(saved, catalog), selectedSlot = 'torso', showAll = false;
  try { localStorage.setItem(STORAGE_KEY, serializeBuild(build)); } catch { /* Storage is optional. */ }
  let workshop, rendering = 0;
  try { workshop = createWorkshop($('viewport')); } catch {
    $('loading').hidden = true;
    $('model-error').hidden = false;
    $('model-error').querySelector('span').textContent = '3D preview needs WebGL. Enable graphics acceleration or try another browser.';
    $('retry').textContent = 'Reload';
    $('retry').onclick = () => location.reload();
  }
  const chinaSuppliers = new Set(['Seeed Studio', 'Waveshare', 'Elephant Robotics', 'Unitree Robotics']);
  const suppliers = [...new Set(catalog.map(p => p.supplier))].sort((a,b) => Number(chinaSuppliers.has(a)) - Number(chinaSuppliers.has(b)) || a.localeCompare(b));
  for (const supplier of suppliers) {
    const option = document.createElement('option'); option.textContent = supplier; option.value = supplier; $('supplier').append(option);
  }
  const icons = { torso: '▣', head: '▤', leftArm: '╱', rightArm: '╲', leftLeg: '▥', rightLeg: '▥' };
  const descriptions = { torso: 'Robot bodies, shells and structural frames.', head: 'Heads and face shells for your robot.', arms: 'Complete arm assemblies with structural links and joints.', legs: 'One shared driving base can fill both leg slots.' };

  function renderBuild() {
    const focus = document.activeElement?.dataset.slot;
    $('slots').innerHTML = SLOTS.map(slot => {
      const part = catalog.find(p => p.id === build.slots[slot.id]);
      const shared = slot.role === 'legs' && isMobileBase(part);
      return `<button class="slot-button ${slot.id === selectedSlot ? 'selected' : ''}" data-slot="${slot.id}" aria-pressed="${slot.id === selectedSlot}" aria-label="Choose ${slot.label.toLowerCase()}: ${escape(part.name)}${shared ? ', shared base' : ''}"><span class="slot-icon" aria-hidden="true">${icons[slot.id]}</span><span class="slot-copy"><strong>${slot.label}${shared ? ' · linked' : ''}</strong><small>${escape(part.name)}</small></span><span class="slot-arrow" aria-hidden="true">›</span></button>`;
    }).join('');
    if (focus) $('slots').querySelector(`[data-slot="${focus}"]`)?.focus({ preventScroll: true });
    const summary = summarizeBuild(build, catalog);
    $('supplier-count').textContent = summary.suppliers.length;
    $('supplier-dots').innerHTML = summary.suppliers.map(supplier => `<span class="supplier-dot" title="${escape(supplier)}" style="background:${catalog.find(p => p.supplier === supplier).color}"></span>`).join('');
    $('parts-count').textContent = `${summary.count} parts`;
    $('bill').innerHTML = summary.lines.map(line => `<div class="bill-line"><span><a href="${escape(line.productUrl)}" target="_blank" rel="noopener noreferrer">${line.quantity} × ${escape(line.name)}</a>${line.note ? `<small class="bill-note">${escape(line.note)}</small>` : ''}</span></div>`).join('');
  }

  function renderCatalog() {
    const slot = SLOTS.find(s => s.id === selectedSlot);
    const query = $('search').value.trim().toLowerCase();
    const supplier = $('supplier').value;
    const parts = catalog.filter(p => (showAll || p.roles.includes(slot.role)) && (!supplier || p.supplier === supplier) && `${p.name} ${p.fullName} ${p.supplier} ${p.sku}`.toLowerCase().includes(query));
    parts.sort((a,b) => Number(chinaSuppliers.has(a.supplier)) - Number(chinaSuppliers.has(b.supplier)) || Number(b.modelKind === 'robot_section') - Number(a.modelKind === 'robot_section'));
    $('catalog-title').textContent = slot.label;
    $('catalog-description').textContent = showAll ? 'Try any part in this slot. There are no fit rules here.' : descriptions[slot.role];
    $('result-count').textContent = parts.length;
    $('all-parts').setAttribute('aria-pressed', String(showAll));
    $('all-parts').textContent = showAll ? 'Suggested parts' : 'All body parts';
    $('empty').hidden = parts.length > 0;
    const focusedPart = document.activeElement?.dataset.part;
    $('catalog').innerHTML = parts.map(part => {
      const selected = build.slots[selectedSlot] === part.id;
      const hint = part.modelKind === 'approximate_preview' ? 'Approximate preview' : part.partType === 'mobile_base' ? 'Shared leg base' : part.modelKind === 'robot_section' ? 'Robot body section' : ({ robotic_arm_kit: 'Complete arm assembly', body_shell: 'Empty body shell', head_shell: 'Empty head shell', chassis_frame: 'Structural frame' }[part.partType] || { actuators: 'Motor / joint component', sensors: 'Sensor component', support: 'Electronics / power', wheels: 'Wheel component' }[part.roles[0]] || '');
      return `<button class="part-card ${selected ? 'selected' : ''}" data-part="${part.id}" aria-pressed="${selected}" aria-label="Use ${escape(part.name)} from ${escape(part.supplier)} for ${slot.label.toLowerCase()}"${part.note ? ` title="${escape(part.note)}"` : ''}><span class="part-image"><img src="${import.meta.env.BASE_URL + part.thumbnail}" alt="" loading="lazy" />${selected ? '<span class="part-check" aria-hidden="true">✓</span>' : ''}</span><span class="part-copy"><span class="part-supplier">${escape(part.supplier)}</span><strong class="part-name">${escape(part.name)}</strong>${hint ? `<span class="part-hint">${hint}</span>` : ''}<span class="part-bottom"><span>3D model</span><span class="add-symbol" aria-hidden="true">${selected ? '✓' : '+'}</span></span></span></button>`;
    }).join('');
    if (focusedPart) $('catalog').querySelector(`[data-part="${focusedPart}"]`)?.focus({ preventScroll: true });
  }

  async function renderModel() {
    if (!workshop) return;
    const token = ++rendering;
    $('export').disabled = true;
    $('loading').hidden = false;
    $('model-error').hidden = true;
    $('viewport').setAttribute('aria-busy', 'true');
    try {
      if (await workshop.update(build, catalog) && token === rendering) $('export').disabled = false;
    } catch (error) {
      if (token === rendering) {
        $('model-error').hidden = false;
        $('model-error').querySelector('span').textContent = 'The new selection could not load. The previous preview is still shown.';
        console.error(error);
      }
    } finally {
      if (token === rendering) { $('loading').hidden = true; $('viewport').setAttribute('aria-busy', 'false'); }
    }
  }

  function changed() {
    try { localStorage.setItem(STORAGE_KEY, serializeBuild(build)); } catch { notify('Browser storage is unavailable. Use Save build to keep your choices.'); }
    renderBuild(); renderCatalog(); renderModel();
  }
  $('slots').addEventListener('click', event => {
    const button = event.target.closest('[data-slot]');
    if (!button) return;
    selectedSlot = button.dataset.slot;
    renderBuild(); renderCatalog();
  });
  $('catalog').addEventListener('click', event => {
    const button = event.target.closest('[data-part]');
    if (!button) return;
    build = setPart(build, selectedSlot, button.dataset.part, catalog);
    changed();
    const shared = ['leftLeg', 'rightLeg'].includes(selectedSlot) && isMobileBase(catalog.find(p => p.id === button.dataset.part));
    notify(shared ? 'Shared base updated for both legs' : `${SLOTS.find(s => s.id === selectedSlot).label} updated`);
  });
  $('search').addEventListener('input', renderCatalog);
  $('supplier').addEventListener('change', renderCatalog);
  $('all-parts').onclick = () => { showAll = !showAll; renderCatalog(); };
  $('clear-filters').onclick = () => { $('search').value = ''; $('supplier').value = ''; renderCatalog(); $('search').focus(); };
  $('reset').onclick = () => { build = createBuild(catalog); changed(); notify('Original combination restored'); };
  $('shuffle').onclick = () => {
    for (const slot of SLOTS) {
      if (slot.id === 'rightLeg' && isMobileBase(catalog.find(p => p.id === build.slots.leftLeg))) continue;
      const choices = catalog.filter(p => p.roles.includes(slot.role));
      build = setPart(build, slot.id, choices[Math.floor(Math.random() * choices.length)].id, catalog);
    }
    changed(); notify('A new combination to make your own');
  };
  $('save').onclick = () => { download(serializeBuild(build), 'my-robot.json', 'application/json'); notify('Build saved. This browser also remembers your choices.'); };
  $('export').onclick = async () => {
    const token = rendering;
    $('export').disabled = true;
    try { download(await workshop.exportRobot(), 'my-robot.glb', 'model/gltf-binary'); notify('Robot exported as GLB — ready for Blender'); }
    catch { notify('The export failed. Please try again.'); }
    finally { if (token === rendering) $('export').disabled = false; }
  };
  if (workshop) {
    $('retry').onclick = renderModel;
    $('front').onclick = () => workshop.front();
    $('rotate-left').onclick = () => workshop.rotate(-1);
    $('rotate-right').onclick = () => workshop.rotate(1);
    $('spread').onclick = () => $('spread').setAttribute('aria-pressed', String(workshop.toggleSpread()));
  } else {
    for (const id of ['front', 'rotate-left', 'rotate-right', 'spread']) $(id).disabled = true;
  }
  renderBuild(); renderCatalog(); await renderModel();
}

start().catch(error => {
  $('loading').hidden = true;
  $('model-error').hidden = false;
  $('model-error').querySelector('span').textContent = error.message || 'The workshop could not start.';
  $('retry').onclick = () => location.reload();
  for (const id of ['save', 'shuffle', 'export']) $(id).disabled = true;
});
