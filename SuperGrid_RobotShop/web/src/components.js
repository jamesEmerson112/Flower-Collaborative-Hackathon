// Components tray: a "Body parts | Components" toggle in the catalog panel, a searchable list of
// store components grouped by part type with -/qty/+ controls, and the picked components in the
// left build panel. Selections persist under their own localStorage key (build.js stays at v4).
// No prices anywhere: cost comes only from the store SuperNodes' quotes.
import {
  MAX_COMPONENT_QTY, componentTotal, groupComponents, parseStoredComponents, partTypeSingular,
  serializeComponents, setComponentQty, starterPicks,
} from './components-data.js';

const escape = value => String(value).replace(/[&<>"']/g, character => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[character]));

export function mountComponents({ components, storageKey, onChange = () => {}, notify = () => {} }) {
  const $ = id => document.getElementById(id);
  const byId = new Map(components.map(component => [component.id, component]));
  let stored = null;
  try { stored = localStorage.getItem(storageKey); } catch { /* The tray works without browser storage. */ }
  let qty = parseStoredComponents(stored, new Set(byId.keys()));
  let mode = 'body', storageWarned = false;

  function save() {
    try { localStorage.setItem(storageKey, serializeComponents(qty)); } catch {
      if (!storageWarned) notify('Browser storage is unavailable, so components reset on reload.');
      storageWarned = true;
    }
  }

  function setMode(next) {
    mode = next === 'components' ? 'components' : 'body';
    $('body-mode').hidden = mode !== 'body';
    $('components-mode').hidden = mode !== 'components';
    $('mode-body').setAttribute('aria-pressed', String(mode === 'body'));
    $('mode-components').setAttribute('aria-pressed', String(mode === 'components'));
  }

  function renderTray() {
    const groups = groupComponents(components, $('component-search').value);
    const shown = groups.reduce((sum, group) => sum + group.items.length, 0);
    $('component-count').textContent = shown;
    $('component-empty').hidden = shown > 0 || components.length === 0;
    $('component-unavailable').hidden = components.length > 0;
    $('starter-electronics').disabled = components.length === 0;
    const picked = componentTotal(qty);
    $('components-picked').textContent = picked ? `${picked} picked` : 'None picked yet';
    // Keep keyboard focus on the same control across re-renders.
    const active = document.activeElement?.dataset || {};
    const focusId = active.inc || active.dec, focusKind = active.inc ? 'inc' : 'dec';
    $('component-list').innerHTML = groups.map(group => `<section class="component-group" aria-label="${escape(group.label)}"><h3>${escape(group.label)}<span>${group.items.length}</span></h3>${group.items.map(component => {
      const n = qty[component.id] || 0;
      return `<div class="component-row${n ? ' picked' : ''}"><div class="component-copy" title="${escape(component.summary || component.name)}"><strong>${escape(component.name)}</strong><small>${escape(component.store_name)} · ${escape(partTypeSingular(component.part_type))}</small></div><div class="qty-control" role="group" aria-label="Quantity of ${escape(component.name)}"><button type="button" data-dec="${escape(component.id)}" aria-label="One fewer ${escape(component.name)}"${n ? '' : ' disabled'}>−</button><output>${n}</output><button type="button" data-inc="${escape(component.id)}" aria-label="Add one ${escape(component.name)}"${n >= MAX_COMPONENT_QTY ? ' disabled' : ''}>+</button></div></div>`;
    }).join('')}</section>`).join('');
    if (focusId) {
      const list = $('component-list');
      const target = [...list.querySelectorAll(`[data-${focusKind}]`)].find(el => el.dataset[focusKind] === focusId);
      const fallback = [...list.querySelectorAll('[data-inc]')].find(el => el.dataset.inc === focusId);
      (target && !target.disabled ? target : fallback)?.focus({ preventScroll: true });
    }
  }

  function renderPicks() {
    const ids = Object.keys(qty);
    $('picks-count').textContent = ids.length ? `${componentTotal(qty)} ITEMS` : 'NONE';
    $('component-picks').innerHTML = ids.length
      ? `<ul class="pick-list">${ids.map(id => {
        const component = byId.get(id);
        return `<li class="pick-line"><span class="pick-qty">${qty[id]}×</span><span class="pick-name" title="${escape(`${component.name} · ${component.store_name}`)}">${escape(component.name)}</span><button type="button" class="pick-remove" data-remove="${escape(id)}" aria-label="Remove ${escape(component.name)}">×</button></li>`;
      }).join('')}</ul>`
      : '<button type="button" class="text-button pick-empty" data-open-components>+ Add motors, sensors and power</button>';
  }

  function update(next, message) {
    qty = next;
    save(); renderTray(); renderPicks(); onChange();
    if (message) notify(message);
  }

  $('mode-body').addEventListener('click', () => setMode('body'));
  $('mode-components').addEventListener('click', () => { setMode('components'); });
  $('component-search').addEventListener('input', renderTray);
  $('component-clear').addEventListener('click', () => { $('component-search').value = ''; renderTray(); $('component-search').focus(); });
  $('component-list').addEventListener('click', event => {
    const button = event.target.closest('[data-inc], [data-dec]');
    if (!button || button.disabled) return;
    const id = button.dataset.inc || button.dataset.dec;
    if (!byId.has(id)) return;
    update(setComponentQty(qty, id, (qty[id] || 0) + (button.dataset.inc ? 1 : -1)));
  });
  $('component-picks').addEventListener('click', event => {
    if (event.target.closest('[data-open-components]')) { setMode('components'); $('component-search').focus(); return; }
    const button = event.target.closest('[data-remove]');
    if (!button) return;
    const name = byId.get(button.dataset.remove)?.name || 'Component';
    update(setComponentQty(qty, button.dataset.remove, 0), `${name} removed`);
  });
  $('starter-electronics').addEventListener('click', () => {
    const picks = starterPicks(components, qty);
    if (!picks.length) { notify('Every store already has a component in your build'); return; }
    let next = qty;
    for (const id of picks) next = setComponentQty(next, id, 1);
    update(next, `Added ${picks.length} starter part${picks.length === 1 ? '' : 's'}, one from each remaining store`);
  });

  setMode('body'); renderTray(); renderPicks();
  return {
    qty: () => qty,
    setMode,
    clear: () => update({}),
  };
}
