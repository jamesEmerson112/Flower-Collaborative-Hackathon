// Quote panel: sends the build to the master (via the local bridge) and shows the stores' quotes.
//
// Flow: POST /api/run {prompt, federation} -> the bridge starts one run on the SuperLink and streams
// its events back as NDJSON (C5). The master fans the parts list out to every store SuperNode,
// emits one `robotshop.quote` event with the combined quote (C4), then writes the answer text.
// If that custom event never arrives, the quote is read from the fenced ```robotshop-quote block
// the master appends to its answer text.
//
// This module touches no DOM at import time (Node's test runner imports it); styles live in
// quote.css, which main.js imports. Every value that reaches innerHTML is escaped first.

export const DEFAULT_REQUEST = 'Build this robot for me';
export const DEFAULT_FEDERATION = '@efebahadirgur/Spartan';
const QUOTE_FENCE = '```robotshop-quote';
const STOP_GRACE_MS = 15000; // after /api/stop, stop listening if the stream hasn't ended by then

// ------------------------------------------------------------------ pure helpers (tested)

const HTML_ESCAPES = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };

export function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>"']/g, (c) => HTML_ESCAPES[c]);
}

/**
 * Split streamed NDJSON text into parsed objects.
 * `carry` is the unfinished tail from the previous chunk; pass the returned `carry` into the next
 * call, and call once more with chunkText '\n' when the stream ends to flush the last line.
 * Blank lines and lines that aren't a JSON object are skipped.
 * A `kind: "run"` line also gets `run_id_str`: the exact digits of run_id (a 64-bit ID loses
 * precision as a JS number, and /api/stop needs the exact value).
 */
export function parseNdjsonChunks(chunkText, carry = '') {
  const parts = `${carry ?? ''}${chunkText ?? ''}`.split('\n');
  const rest = parts.pop();
  const lines = [];
  for (const raw of parts) {
    const text = raw.trim();
    if (!text) continue;
    let obj;
    try {
      obj = JSON.parse(text);
    } catch {
      continue;
    }
    if (!obj || typeof obj !== 'object' || Array.isArray(obj)) continue;
    if (obj.kind === 'run') {
      const digits = text.match(/"run_id"\s*:\s*"?(\d+)"?/);
      if (digits) obj.run_id_str = digits[1];
    }
    lines.push(obj);
  }
  return { lines, carry: rest };
}

function parseJson(text) {
  if (typeof text !== 'string') return text && typeof text === 'object' ? text : null;
  try {
    return JSON.parse(text);
  } catch {
    return null;
  }
}

function plural(n, one, many = `${one}s`) {
  return `${n} ${n === 1 ? one : many}`;
}

// Accepts a bridge line ({kind: "event", type, payload}) or a bare event ({type, ...}).
function eventOf(line) {
  if (!line || typeof line !== 'object') return null;
  if (line.kind !== undefined && line.kind !== 'event') return null;
  const payload = line.payload && typeof line.payload === 'object' ? line.payload : line;
  return { type: String(line.type ?? payload.type ?? ''), payload };
}

/** One progress sentence for a bridge line, or null if the line isn't a progress step. */
export function progressFrom(line) {
  const event = eventOf(line);
  if (!event) return null;
  const { type, payload } = event;
  if (type === 'function_call') {
    if (payload.name === 'get_nodes') return 'Finding store nodes…';
    if (payload.name === 'push_messages') {
      const messages = parseJson(payload.arguments)?.messages;
      return Array.isArray(messages) ? `Asking ${plural(messages.length, 'store')}…` : 'Asking the stores…';
    }
    if (payload.name === 'pull_messages') return 'Collecting quotes…';
    return null;
  }
  if (type === 'robotshop.progress') {
    const replied = Number(payload.replied);
    const expected = Number(payload.expected);
    if (Number.isFinite(replied) && Number.isFinite(expected)) {
      return `${replied} of ${plural(expected, 'store')} answered…`;
    }
    return 'Collecting quotes…';
  }
  if (type === 'robotshop.quote') return 'Writing the answer…';
  return null;
}

/**
 * Pull the master's fenced quote block out of the answer text.
 * Returns {text, quote}: `text` without the block (always stripped), `quote` the parsed Q or null.
 * With {streaming: true} it also hides a block that has only partly arrived.
 * Falls back to a ```json block holding an object with `lines` and `totals`.
 */
export function extractQuoteBlock(text, { streaming = false } = {}) {
  let rest = String(text ?? '');
  let quote = null;

  const fenced = /(?:^|\n)[ \t]*```robotshop-quote[ \t]*\r?\n([\s\S]*?)\r?\n[ \t]*```[ \t]*(?=\r?\n|$)/g;
  rest = rest.replace(fenced, (_, body) => {
    const parsed = parseJson(body.trim());
    if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) quote = parsed;
    return '';
  });

  // An opening fence with no closing fence: the block is cut off (or still streaming).
  const open = rest.indexOf(QUOTE_FENCE);
  if (open >= 0) {
    if (!quote) {
      const parsed = parseJson(rest.slice(open + QUOTE_FENCE.length).replace(/```\s*$/, '').trim());
      if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) quote = parsed;
    }
    rest = rest.slice(0, open);
  } else if (streaming) {
    // Hide a partly arrived opening marker at the very end ("```", "```robot…").
    for (let k = QUOTE_FENCE.length - 1; k >= 3; k -= 1) {
      if (rest.endsWith(QUOTE_FENCE.slice(0, k))) {
        rest = rest.slice(0, rest.length - k);
        break;
      }
    }
  }

  if (!quote) {
    const jsonFence = /(?:^|\n)[ \t]*```json[ \t]*\r?\n([\s\S]*?)\r?\n[ \t]*```[ \t]*(?=\r?\n|$)/g;
    rest = rest.replace(jsonFence, (block, body) => {
      const parsed = parseJson(body.trim());
      if (parsed && typeof parsed === 'object' && Array.isArray(parsed.lines) && parsed.totals) {
        quote = parsed;
        return '';
      }
      return block;
    });
  }

  return { text: rest.replace(/\s+$/, ''), quote };
}

function inlineMarkdown(escaped) {
  const codes = [];
  let s = escaped.replace(/`([^`\n]+)`/g, (_, code) => {
    codes.push(code);
    return `\u0000${codes.length - 1}\u0000`;
  });
  // Links only to http(s); the text is already escaped, so the captured URL holds no quotes or tags.
  s = s.replace(/\[([^\]\n]+)\]\((https?:\/\/[^\s)]+)\)/g,
    '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>');
  s = s.replace(/\*\*([^*\n]+?)\*\*/g, '<strong>$1</strong>');
  return s.replace(/\u0000(\d+)\u0000/g, (_, i) => `<code>${codes[Number(i)]}</code>`);
}

/** Minimal, safe markdown: everything is escaped, then **bold**, `code`, [links](https://…),
 *  "- " bullet lists, "#" headings (shown as a bold line) and line breaks. */
export function renderMarkdown(text) {
  const lines = escapeHtml(String(text ?? '').replace(/\u0000/g, '')).replace(/\r\n?/g, '\n').split('\n');
  const out = [];
  let para = [];
  let list = null;
  const flushPara = () => {
    if (para.length) out.push(`<p>${para.join('<br>')}</p>`);
    para = [];
  };
  const flushList = () => {
    if (list) out.push(`<ul>${list.map((item) => `<li>${item}</li>`).join('')}</ul>`);
    list = null;
  };
  for (const raw of lines) {
    const line = raw.replace(/\s+$/, '');
    const bullet = line.match(/^\s*[-*•]\s+(.*)$/);
    if (bullet) {
      flushPara();
      (list ??= []).push(inlineMarkdown(bullet[1]));
      continue;
    }
    flushList();
    if (!line.trim()) {
      flushPara();
      continue;
    }
    const heading = line.match(/^\s{0,3}#{1,6}\s+(.*)$/);
    if (heading) {
      flushPara();
      out.push(`<p class="rq-md-heading">${inlineMarkdown(heading[1])}</p>`);
      continue;
    }
    para.push(inlineMarkdown(line.trim()));
  }
  flushPara();
  flushList();
  return out.join('');
}

const moneyFormats = new Map();

export function formatMoney(amount, currency = 'USD') {
  const n = Number(amount);
  if (amount === null || amount === undefined || amount === '' || !Number.isFinite(n)) return '—';
  const code = String(currency || 'USD').trim().toUpperCase();
  if (!moneyFormats.has(code)) {
    let format = null;
    try {
      format = new Intl.NumberFormat('en-US', { style: 'currency', currency: code });
    } catch {
      format = null; // unknown currency code
    }
    moneyFormats.set(code, format);
  }
  const format = moneyFormats.get(code);
  return format ? format.format(n) : `${n.toFixed(2)} ${code}`;
}

const toCents = (value) => Math.round(Number(value) * 100);
const asArray = (value) => (Array.isArray(value) ? value.filter((v) => v && typeof v === 'object') : []);
const safeUrl = (url) => (typeof url === 'string' && /^https?:\/\//i.test(url.trim()) ? url.trim() : null);
const qtyOf = (value) => (Number.isFinite(Number(value)) && Number(value) > 0 ? Number(value) : 1);

function lineSubtotal(line) {
  if (Number.isFinite(Number(line.subtotal)) && line.subtotal !== null && line.subtotal !== '') return Number(line.subtotal);
  const unit = Number(line.unit_price);
  return Number.isFinite(unit) && line.unit_price !== null ? (toCents(unit) * qtyOf(line.qty)) / 100 : null;
}

// Sum a list of {amount, currency} in integer cents, per currency.
function sumByCurrency(entries) {
  const cents = new Map();
  for (const { amount, currency } of entries) {
    if (amount === null || !Number.isFinite(Number(amount))) continue;
    const code = String(currency || 'USD').toUpperCase();
    cents.set(code, (cents.get(code) ?? 0) + toCents(amount));
  }
  return [...cents].map(([currency, c]) => ({ currency, amount: c / 100 }));
}

function renderLine(line) {
  const qty = qtyOf(line.qty);
  const currency = line.currency || 'USD';
  const name = escapeHtml(line.name || line.product_id || 'Unnamed part');
  const url = safeUrl(line.url);
  const title = line.sku ? ` title="SKU ${escapeHtml(line.sku)}"` : '';
  const label = url
    ? `<a href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer"${title}>${name}</a>`
    : `<span${title}>${name}</span>`;
  return `<li class="rq-line">`
    + `<span class="rq-line-name"><span class="rq-qty">${escapeHtml(qty)} ×</span> ${label}</span>`
    + `<span class="rq-line-price"><span class="rq-unit">${escapeHtml(formatMoney(line.unit_price, currency))} each</span>`
    + `<strong>${escapeHtml(formatMoney(lineSubtotal(line), currency))}</strong></span>`
    + `</li>`;
}

function renderStatus(nodes) {
  if (!nodes || typeof nodes !== 'object') return '';
  const n = (v) => (Number.isFinite(Number(v)) ? Number(v) : 0);
  const replied = n(nodes.stores_replied);
  const asked = n(nodes.asked);
  const noCatalog = n(nodes.no_catalog);
  const errors = Array.isArray(nodes.errors) ? nodes.errors : [];
  const errorCount = Array.isArray(nodes.errors) ? errors.length : n(nodes.errors);
  const timedOut = n(nodes.timed_out);

  let text;
  if (nodes.targeted) {
    text = `${replied} of ${plural(asked, 'store node')} answered`;
  } else {
    const extra = [`${plural(asked, 'node')} asked`];
    if (noCatalog > 0) extra.push(`${noCatalog} without a catalogue`);
    text = `${plural(replied, 'store node')} answered (${extra.join(', ')})`;
  }
  const problems = [];
  if (errorCount > 0) problems.push(plural(errorCount, 'error'));
  if (timedOut > 0) problems.push(`${timedOut} timed out`);
  const bad = problems.length ? ` <span class="rq-status-bad">· ${escapeHtml(problems.join(' · '))}</span>` : '';
  const details = errors.length
    ? `<ul class="rq-errors">${errors.map((e) => `<li>node ${escapeHtml(e.node_id ?? '?')}: ${escapeHtml(e.message ?? e.code ?? 'error')}</li>`).join('')}</ul>`
    : '';
  return `<p class="rq-status">${escapeHtml(text)}${bad}</p>${details}`;
}

function renderUnquoted(list, heading, withReason) {
  if (!list.length) return '';
  const items = list.map((u) => {
    const reason = withReason && u.reason ? ` <span class="rq-reason">— ${escapeHtml(u.reason)}</span>` : '';
    return `<li><span class="rq-qty">${escapeHtml(qtyOf(u.qty))} ×</span> ${escapeHtml(u.name || u.product_id || 'Unnamed part')}${reason}</li>`;
  }).join('');
  return `<section class="rq-unquoted"><h4 class="rq-eyebrow">${escapeHtml(heading)}</h4><ul>${items}</ul></section>`;
}

/** HTML for one combined quote Q (contract C4). Every value is escaped. */
export function renderQuoteHtml(Q) {
  if (!Q || typeof Q !== 'object') return '<p class="rq-empty">No quote came back.</p>';
  const lines = asArray(Q.lines);
  const stores = asArray(Q.stores);
  const unquoted = asArray(Q.unquoted);

  // Group lines by store, in the order of Q.stores, then any store only the lines mention.
  const keyOf = (o) => String(o.store_id ?? o.node_id ?? o.store_name ?? '?');
  const groups = new Map();
  for (const store of stores) if (!groups.has(keyOf(store))) groups.set(keyOf(store), { store, lines: [] });
  for (const line of lines) {
    const key = keyOf(line);
    if (!groups.has(key)) {
      groups.set(key, { store: { store_id: line.store_id, store_name: line.store_name, node_id: line.node_id }, lines: [] });
    }
    groups.get(key).lines.push(line);
  }

  // Totals: Q.totals is authoritative; recompute from the lines only if it's missing.
  let totals = Q.totals && typeof Q.totals === 'object' && !Array.isArray(Q.totals)
    ? Object.entries(Q.totals).map(([currency, amount]) => ({ currency, amount }))
    : sumByCurrency(lines.map((l) => ({ amount: lineSubtotal(l), currency: l.currency })));
  totals = totals.filter((t) => t.amount !== null && Number.isFinite(Number(t.amount)));

  const parts = ['<div class="rq-quote">'];
  if (totals.length) {
    const amounts = totals.map((t) => `<strong class="rq-sum-amount">${escapeHtml(formatMoney(t.amount, t.currency))}</strong>`).join('');
    const note = totals.length > 1 ? '<span class="rq-note">Not converted between currencies.</span>' : '';
    parts.push(`<div class="rq-sum"><span class="rq-eyebrow">Quoted by the stores</span>${amounts}${note}</div>`);
  } else {
    parts.push('<div class="rq-sum rq-sum-none"><span class="rq-eyebrow">Quoted by the stores</span><strong class="rq-sum-amount">—</strong></div>');
  }
  parts.push(renderStatus(Q.nodes));

  const filled = [...groups.values()].filter((g) => g.lines.length);
  if (filled.length) {
    for (const { store, lines: storeLines } of filled) {
      const currency = store.currency || storeLines[0].currency || 'USD';
      const subtotal = store.subtotal !== undefined && store.subtotal !== null && Number.isFinite(Number(store.subtotal))
        ? escapeHtml(formatMoney(store.subtotal, currency))
        : sumByCurrency(storeLines.map((l) => ({ amount: lineSubtotal(l), currency: l.currency || currency })))
          .map((t) => escapeHtml(formatMoney(t.amount, t.currency))).join(' + ') || '—';
      const name = escapeHtml(store.store_name || store.store_id || `node ${store.node_id ?? '?'}`);
      parts.push(`<section class="rq-store">`
        + `<header class="rq-store-head"><span class="rq-store-name">${name}</span><span class="rq-store-sub">${subtotal}</span></header>`
        + `<ul class="rq-lines">${storeLines.map(renderLine).join('')}</ul>`
        + `</section>`);
    }
  } else {
    parts.push('<p class="rq-empty">No store quoted any of these parts.</p>');
  }

  const noStore = unquoted.filter((u) => !u.code || u.code === 'no_store');
  const notQuoted = unquoted.filter((u) => u.code && u.code !== 'no_store');
  parts.push(renderUnquoted(noStore, 'No store sells it', false));
  parts.push(renderUnquoted(notQuoted, 'Not quoted', true));
  parts.push('</div>');
  return parts.join('');
}

// ------------------------------------------------------------------ run log text (pure)

const shorten = (s, n = 140) => {
  const text = String(s ?? '');
  return text.length > n ? `${text.slice(0, n)}…` : text;
};

/** [text, cssClass] for the "Flower run" log, ported from SuperNode_James/master-ui. */
export function logEntryFor(type, payload = {}) {
  const p = payload && typeof payload === 'object' ? payload : {};
  if (type === 'function_call') return [`→ ${p.name ?? '?'} ${shorten(p.arguments)}`, 'call'];
  if (type === 'function_call_output') return [`← ${shorten(p.output)}`, 'out'];
  if (type === 'message') return [`${p.role ?? 'message'}: ${shorten(p.content)}`, ''];
  if (type === 'response.output_text.delta') return [`text (${String(p.delta ?? '').length} chars)`, ''];
  if (type === 'robotshop.progress') {
    const stores = Array.isArray(p.stores) && p.stores.length ? `: ${p.stores.join(', ')}` : '';
    return [`robotshop.progress ${p.replied ?? '?'} of ${p.expected ?? '?'} answered${stores}`, 'call'];
  }
  if (type === 'robotshop.quote') {
    const q = p.quote && typeof p.quote === 'object' ? p.quote : {};
    return [`robotshop.quote (${plural(asArray(q.lines).length, 'line')}, ${plural(asArray(q.stores).length, 'store')}, ${asArray(q.unquoted).length} unquoted)`, 'end'];
  }
  const bad = type === 'error' || /fail|incomplete|error/.test(type);
  return [type || '(event)', type === 'response.completed' ? 'end' : bad ? 'bad' : ''];
}

// ------------------------------------------------------------------ cache mode (pure)
//
// SuperGrid queues runs for 2–3 minutes, so the bridge records every successful live run and
// POST /api/cache {prompt} returns the last one for the same prompt string:
//   200 {key, saved_at, run_id, request, items, lines: [bridge lines in order]}  or  404 {error}.
// The page replays those lines through the same handler as a live stream, labelled as cached.

export const CACHE_MODE_KEY = 'supergrid.robot-shop.cache-mode';
export const CACHE_OFFER_MS = 30000; // live run still queued this long after its run line: offer the cache
const REPLAY_LINE_MS = 120;
const REPLAY_DELTA_MS = 20;
const REPLAY_MAX_MS = 8000;

const isDeltaLine = (line) => line?.kind === 'event' && line.type === 'response.output_text.delta';

/**
 * Normalise a 200 body from /api/cache. Returns {key, runId, savedAt, request, items, lines}, or null
 * when it holds no replayable lines. The lines went through JSON.parse, so a 64-bit run_id on the
 * run line is a rounded number: restore the exact digits from the top-level run_id (a string).
 */
export function normalizeCachedRun(data) {
  if (!data || typeof data !== 'object' || !Array.isArray(data.lines)) return null;
  const top = data.run_id !== undefined && data.run_id !== null ? String(data.run_id).trim() : '';
  const exact = /^\d+$/.test(top) ? top : null;
  const lines = data.lines
    .filter((line) => line && typeof line === 'object' && !Array.isArray(line))
    .map((line) => (line.kind === 'run' && exact ? { ...line, run_id_str: exact } : line));
  if (!lines.length) return null;
  const runLine = lines.find((line) => line.kind === 'run');
  return {
    key: data.key ?? null,
    runId: top || runLine?.run_id_str || (runLine?.run_id != null ? String(runLine.run_id) : null),
    savedAt: data.saved_at ?? null,
    request: data.request ?? null,
    items: Array.isArray(data.items) ? data.items : [],
    lines,
  };
}

/** Local date and time for an ISO timestamp (Python's 6-digit fractions included), or null. */
export function formatSavedAt(iso) {
  if (!iso) return null;
  let date = new Date(String(iso));
  if (Number.isNaN(date.getTime())) date = new Date(String(iso).replace(/(\.\d{3})\d+/, '$1'));
  if (Number.isNaN(date.getTime())) return null;
  try {
    return date.toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' });
  } catch {
    return date.toLocaleString();
  }
}

/** The banner shown above a replayed result. `cache` is normalizeCachedRun's output (or the raw body). */
export function cachedBannerText(cache, { liveStillRunning = false } = {}) {
  const runId = cache?.runId ?? cache?.run_id ?? '?';
  const when = formatSavedAt(cache?.savedAt ?? cache?.saved_at) ?? 'an earlier time';
  const head = `Cached result — recorded from live SuperGrid run ${runId} at ${when}.`;
  // After "Show cached result now" Cache mode is already off, so say what's happening instead.
  return liveStillRunning
    ? `${head} The live run is still finishing at Flower in the background.`
    : `${head} Turn off Cache mode for a live run.`;
}

/**
 * Delay in ms before each line of a replay: 0 for the first, ~120 ms per line, faster for text
 * deltas, and scaled down so the whole replay takes at most `maxTotalMs`.
 */
export function replayDelays(lines, { lineMs = REPLAY_LINE_MS, deltaMs = REPLAY_DELTA_MS, maxTotalMs = REPLAY_MAX_MS } = {}) {
  const list = Array.isArray(lines) ? lines : [];
  const delays = list.map((line, i) => (i === 0 ? 0 : isDeltaLine(line) ? deltaMs : lineMs));
  const sum = delays.reduce((n, d) => n + d, 0);
  if (sum <= maxTotalMs || sum === 0) return delays;
  const scale = maxTotalMs / sum;
  return delays.map((d) => Math.round(d * scale));
}

/**
 * Fold bridge lines (live or cached) into what they add up to, without touching the DOM:
 * {runId, quote, quoteFromEvent, text, answer, steps, completed, done, terminalSeen, error}.
 * `answer` is the text without the fenced quote block; `quote` falls back to that block.
 */
export function summarizeRunLines(lines) {
  const out = {
    runId: null, quote: null, quoteFromEvent: false, text: '', answer: '', steps: [],
    completed: false, done: false, terminalSeen: false, error: null,
  };
  for (const line of asArray(lines)) {
    if (line.kind === 'run') {
      out.runId = line.run_id_str ?? (line.run_id != null ? String(line.run_id) : null);
    } else if (line.kind === 'event') {
      const type = String(line.type ?? '');
      const payload = line.payload && typeof line.payload === 'object' ? line.payload : {};
      const step = progressFrom(line);
      if (step) out.steps.push(step);
      if (type === 'robotshop.quote' && payload.quote && typeof payload.quote === 'object') {
        out.quote = payload.quote;
        out.quoteFromEvent = true;
      } else if (type === 'response.output_text.delta' && typeof payload.delta === 'string') {
        out.text += payload.delta;
      } else if (type === 'response.completed') {
        out.completed = true;
      }
    } else if (line.kind === 'done') {
      out.done = true;
      out.terminalSeen = Boolean(line.terminal_seen);
    } else if (line.kind === 'error') {
      out.error = String(line.message ?? 'Unknown error');
    }
  }
  const { text, quote } = extractQuoteBlock(out.text);
  out.answer = text;
  if (!out.quote && quote) out.quote = quote;
  return out;
}

/** True when a cached run actually holds something worth showing (a quote or answer text). */
export function cacheHasResult(cache) {
  if (!cache || !Array.isArray(cache.lines)) return false;
  const summary = summarizeRunLines(cache.lines);
  return Boolean(summary.quote || summary.answer.trim());
}

// ------------------------------------------------------------------ the panel (browser only)

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

async function errorFromResponse(res) {
  let detail = '';
  try {
    const raw = await res.text();
    const parsed = parseJson(raw);
    detail = parsed && typeof parsed === 'object' && parsed.error ? String(parsed.error) : '';
    if (!detail && raw && !/^\s*</.test(raw)) detail = raw.trim().slice(0, 200);
  } catch {
    detail = '';
  }
  if (res.status === 401) return `The bridge refused the request: ${detail || 'missing or wrong token'}. Open the page with ?token=… if the bridge uses BRIDGE_TOKEN.`;
  if (res.status >= 500 || res.status === 404) {
    return `Can't reach the bridge (${res.status}${detail ? `: ${detail}` : ''}). Start it with: python SuperGrid_RobotShop/bridge.py`;
  }
  return detail || `${res.status} ${res.statusText}`;
}

function readCacheMode() {
  try {
    return globalThis.localStorage?.getItem(CACHE_MODE_KEY) === '1';
  } catch {
    return false;
  }
}

function writeCacheMode(on) {
  try {
    globalThis.localStorage?.setItem(CACHE_MODE_KEY, on ? '1' : '0');
  } catch {
    // storage blocked (private window, previews): the toggle still works for this page load
  }
}

const abortError = () => new DOMException('The operation was aborted.', 'AbortError');

function wait(ms, signal) {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) {
      reject(abortError());
      return;
    }
    const onAbort = () => {
      clearTimeout(timer);
      reject(abortError());
    };
    const timer = setTimeout(() => {
      signal?.removeEventListener('abort', onAbort);
      resolve();
    }, Math.max(0, ms));
    signal?.addEventListener('abort', onAbort, { once: true });
  });
}

/**
 * Mount the quote panel into `container` (contract C6).
 * getItems() returns C1 items: [{product_id, qty, name, store_id}].
 * Returns {root, run, stop, isRunning, isCacheMode, setCacheMode}.
 *
 * Cache mode (toggle, remembered in localStorage): Build replays the last live run the bridge
 * recorded for the same prompt (POST /api/cache) instead of queueing a new one. In a live run that
 * is still queued CACHE_OFFER_MS after its run line, a "Show cached result now" button appears when
 * a cached run exists; it stops listening locally (no /api/stop: the bridge keeps draining the run
 * and refreshes the cache) and replays the cached lines. Replays are always labelled as cached.
 */
export function mountQuote(container, { getItems, federation = DEFAULT_FEDERATION, endpoint = '', token } = {}) {
  if (!container) throw new Error('mountQuote needs a container element');
  const base = String(endpoint || '').replace(/\/+$/, '');
  let bridgeToken = token;
  if (bridgeToken === undefined) {
    try {
      bridgeToken = new URLSearchParams(globalThis.location?.search ?? '').get('token') || null;
    } catch {
      bridgeToken = null;
    }
  }
  const headers = () => {
    const h = { 'Content-Type': 'application/json' };
    if (bridgeToken) h['X-Bridge-Token'] = bridgeToken;
    return h;
  };

  // ---- DOM
  const root = el('div', 'rq');
  const head = el('div', 'rq-head');
  head.append(el('span', 'rq-eyebrow', 'Ask the stores'), el('h2', 'rq-title', 'Get quotes from the stores'));
  const intro = el('p', 'rq-intro', 'Each store runs its own Flower SuperNode and prices only the parts it sells, from its private catalogue.');
  const promptId = `rq-prompt-${Math.random().toString(36).slice(2, 8)}`;
  const label = el('label', 'rq-label', 'Your request');
  label.htmlFor = promptId;
  const prompt = el('textarea', 'rq-prompt');
  prompt.id = promptId;
  prompt.rows = 2;
  prompt.value = DEFAULT_REQUEST;
  prompt.placeholder = DEFAULT_REQUEST;
  const actions = el('div', 'rq-actions');
  const buildButton = el('button', 'rq-button rq-build', 'Build this robot');
  buildButton.type = 'button';
  const stopButton = el('button', 'rq-button rq-stop', 'Stop');
  stopButton.type = 'button';
  stopButton.hidden = true;
  const cacheToggle = el('label', 'rq-cache');
  const cacheInput = el('input', 'rq-cache-input');
  cacheInput.type = 'checkbox';
  cacheInput.checked = readCacheMode();
  cacheToggle.append(cacheInput, el('span', 'rq-cache-text', 'Cache mode — replay the last live run for this build'));
  actions.append(buildButton, stopButton, cacheToggle);
  const progressRow = el('div', 'rq-progress-row');
  const progress = el('p', 'rq-progress');
  progress.setAttribute('role', 'status');
  progress.setAttribute('aria-live', 'polite');
  const cacheNowButton = el('button', 'rq-button rq-cache-now', 'Show cached result now');
  cacheNowButton.type = 'button';
  cacheNowButton.hidden = true;
  progressRow.append(progress, cacheNowButton);
  const message = el('div', 'rq-message');
  message.hidden = true;
  const banner = el('div', 'rq-cached');
  banner.setAttribute('role', 'note');
  banner.hidden = true;
  const result = el('div', 'rq-result');
  const answer = el('div', 'rq-answer');
  answer.hidden = true;
  const log = el('details', 'rq-log');
  const summary = el('summary', '', 'Flower run');
  const logCount = el('span', 'rq-log-count', '');
  summary.append(logCount);
  const logBody = el('div', 'rq-log-body');
  log.append(summary, logBody);
  log.hidden = true;
  root.append(head, intro, label, prompt, actions, progressRow, message, banner, result, answer, log);
  container.replaceChildren(root);

  // ---- state
  let run = null; // per-run state while running

  const setProgress = (text, kind = '') => {
    progress.textContent = text || '';
    progress.className = `rq-progress${kind ? ` rq-${kind}` : ''}${run && !kind ? ' rq-busy' : ''}`;
  };
  const showMessage = (text, kind = 'warn') => {
    message.textContent = text;
    message.className = `rq-message rq-${kind}`;
    message.setAttribute('role', kind === 'error' ? 'alert' : 'status');
    message.hidden = !text;
  };
  const logLine = (text, cls = '') => {
    const row = el('div', 'rq-log-row');
    row.append(el('span', 'rq-log-time', `${new Date().toLocaleTimeString()} `), el('span', cls ? `rq-log-${cls}` : '', text));
    logBody.append(row);
    logBody.scrollTop = logBody.scrollHeight;
    logCount.textContent = ` · ${logBody.childElementCount}`;
    log.hidden = false;
  };
  const renderQuote = (quote) => {
    result.innerHTML = renderQuoteHtml(quote); // escaped by renderQuoteHtml
  };
  const renderAnswer = (text) => {
    answer.innerHTML = renderMarkdown(text); // escaped by renderMarkdown
    answer.hidden = !text.trim();
  };
  const setRunning = (on) => {
    buildButton.disabled = on;
    buildButton.setAttribute('aria-busy', on ? 'true' : 'false');
    stopButton.hidden = !on;
    stopButton.disabled = false;
    cacheInput.disabled = on; // the mode is fixed when Build is pressed
    root.classList.toggle('rq-running', on);
  };
  const showBanner = (text) => {
    banner.textContent = text || ''; // textContent: nothing here is parsed as HTML
    banner.hidden = !text;
  };
  const hideCacheOffer = () => {
    cacheNowButton.hidden = true;
  };

  // Offer the cached result once both are true: the live run is still queued CACHE_OFFER_MS after
  // its run line, and the background /api/cache probe found a usable run. Either can happen first.
  function maybeOfferCache(current) {
    if (run !== current || current.mode !== 'live') return;
    if (current.offerDue && current.cache && !current.firstEvent && !current.stopRequested && !current.switchedToCache) {
      cacheNowButton.hidden = false;
    }
  }

  // POST /api/cache with the exact prompt string /api/run gets. Returns the normalised cached run,
  // null when there is none for this build, or throws (bridge errors, AbortError).
  async function fetchCache(promptJson, signal) {
    const res = await fetch(`${base}/api/cache`, {
      method: 'POST',
      headers: headers(),
      body: JSON.stringify({ prompt: promptJson }),
      signal,
    });
    if (res.status === 404) {
      const raw = await res.text().catch(() => '');
      const detail = String(parseJson(raw)?.error ?? '');
      if (/cache/i.test(detail)) return null; // {"error": "no cached run for this build"}
      if (/^not found$/i.test(detail.trim())) {
        throw new Error("This bridge doesn't support Cache mode yet (no /api/cache). Restart it with the latest SuperGrid_RobotShop/bridge.py.");
      }
      throw new Error(`Can't reach the bridge (404${detail ? `: ${detail}` : ''}). Start it with: python SuperGrid_RobotShop/bridge.py`);
    }
    if (!res.ok) throw new Error(await errorFromResponse(res));
    return normalizeCachedRun(parseJson(await res.text()));
  }

  // Feed a cached run through handleLine at a watchable pace. Throws AbortError if stopped.
  async function replayCache(current, cache, { liveStillRunning = false } = {}) {
    const signal = current.controller.signal;
    current.replaying = true;
    current.replayed = cache;
    current.replayStarted = Date.now();
    current.firstEvent = false;
    showBanner(cachedBannerText(cache, { liveStillRunning }));
    logLine(`replaying cached run ${cache.runId ?? '?'} (recorded ${formatSavedAt(cache.savedAt) ?? 'earlier'})`, 'call');
    if (!current.stopRequested) setProgress('Replaying the cached run…');
    const delays = replayDelays(cache.lines);
    for (let i = 0; i < cache.lines.length; i += 1) {
      if (delays[i] > 0) await wait(delays[i], signal);
      if (signal.aborted || run !== current) throw abortError();
      handleLine(cache.lines[i]);
    }
  }

  // "Show cached result now": stop listening to the queued live run and replay the cache instead.
  function showCachedNow() {
    const current = run;
    if (!current || current.mode !== 'live' || !current.cache || current.firstEvent || current.stopRequested || current.switchedToCache) return;
    current.switchedToCache = true;
    current.liveRunId = current.runId;
    hideCacheOffer();
    clearInterval(current.waitTimer);
    clearTimeout(current.offerTimer);
    logLine(`stopped listening to live run ${current.runId ?? '?'}; it keeps running at Flower and the bridge will refresh the cache`, 'out');
    // Fresh controller first so Stop can still cancel the replay; then drop the live stream locally.
    const live = current.controller;
    current.controller = new AbortController();
    live.abort();
  }

  function handleLine(line) {
    if (!run || (run.switchedToCache && !run.replaying)) return; // late lines from an abandoned live stream
    if (line.kind === 'run') {
      run.runId = line.run_id_str ?? (line.run_id != null ? String(line.run_id) : null);
      if (run.replaying) {
        logLine(`cached run ${run.runId ?? '?'}${line.app_id ? ` · ${line.app_id}` : ''}`, 'end');
        return; // no queue clock, no /api/stop: this run finished long ago
      }
      logLine(`run ${run.runId ?? '?'} started${line.app_id ? ` · ${line.app_id}` : ''}`, 'end');
      if (!run.stopRequested) {
        // SuperGrid queues runs before starting them (2–3 min seen live), so show a live clock.
        const current = run;
        const t0 = Date.now();
        const tick = () => {
          if (run === current && !current.firstEvent && !current.stopRequested) {
            const s = Math.floor((Date.now() - t0) / 1000);
            setProgress(`Queued at Flower, waiting for the run to start… ${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')} (SuperGrid can take 2–3 min)`);
          }
        };
        tick();
        current.waitTimer = setInterval(tick, 1000);
        current.offerTimer = setTimeout(() => {
          current.offerDue = true;
          maybeOfferCache(current);
        }, CACHE_OFFER_MS);
      } else if (run.runId) requestStop(); // Stop was pressed before the run had an ID
      return;
    }
    if (line.kind === 'event') {
      if (!run.firstEvent) {
        run.firstEvent = true;
        clearInterval(run.waitTimer);
        clearTimeout(run.offerTimer);
        if (!run.replaying) hideCacheOffer(); // the live run started: no need for the cache
      }
      const type = String(line.type ?? '');
      const payload = line.payload && typeof line.payload === 'object' ? line.payload : {};
      const [text, cls] = logEntryFor(type, payload);
      logLine(text, cls);
      const step = progressFrom(line);
      if (step && !run.stopRequested) setProgress(step);
      if (type === 'robotshop.quote' && payload.quote && typeof payload.quote === 'object') {
        run.quote = payload.quote;
        run.quoteFromEvent = true;
        renderQuote(run.quote);
      } else if (type === 'response.output_text.delta' && typeof payload.delta === 'string') {
        run.text += payload.delta;
        renderAnswer(extractQuoteBlock(run.text, { streaming: true }).text);
      } else if (type === 'response.completed') {
        run.completed = true;
      }
      return;
    }
    if (line.kind === 'done') {
      run.done = true;
      run.terminalSeen = Boolean(line.terminal_seen);
      logLine('run finished', 'end');
      return;
    }
    if (line.kind === 'error') {
      run.error = String(line.message ?? 'Unknown error');
      logLine(`error: ${run.error}`, 'bad');
    }
  }

  async function readStream(res) {
    let carry = '';
    const feed = (chunk) => {
      const parsed = parseNdjsonChunks(chunk, carry);
      carry = parsed.carry;
      for (const line of parsed.lines) handleLine(line);
    };
    if (res.body && typeof res.body.getReader === 'function') {
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      for (;;) {
        const { value, done } = await reader.read();
        if (done) break;
        feed(decoder.decode(value, { stream: true }));
      }
      feed(decoder.decode());
    } else {
      feed(await res.text());
    }
    feed('\n');
  }

  function finish() {
    const current = run;
    if (!current) return;
    clearTimeout(current.stopTimer);
    clearInterval(current.waitTimer);
    clearTimeout(current.offerTimer);
    hideCacheOffer();
    const seconds = ((Date.now() - current.started) / 1000).toFixed(1);
    const { text, quote } = extractQuoteBlock(current.text);
    renderAnswer(text);
    if (!current.quote && quote) {
      current.quote = quote;
      renderQuote(quote);
      logLine('quote read from the answer text (no robotshop.quote event arrived)', 'out');
    }
    run = null;
    setRunning(false);

    if (current.cacheMiss && !current.error && !current.stopRequested) {
      setProgress('');
      showMessage('No cached run for this build yet. Turn off Cache mode and run it live once to record it.', 'warn');
      return;
    }
    if (current.error) {
      showMessage(current.error, 'error');
      setProgress(current.stopRequested ? `Stopped after ${seconds} s.` : `Failed after ${seconds} s.`, 'bad');
    } else if (current.stopRequested) {
      setProgress(`Stopped after ${seconds} s.`, 'bad');
    } else if (current.replayed) {
      const replaySeconds = ((Date.now() - current.replayStarted) / 1000).toFixed(1);
      const id = current.replayed.runId ? ` ${current.replayed.runId}` : '';
      setProgress(`Replayed cached run${id} in ${replaySeconds} s.`, 'ok');
      if (!current.done || !current.terminalSeen) {
        showMessage('The cached run ended before the master sent response.completed; the answer may be incomplete.', 'warn');
      }
    } else {
      setProgress(`Done in ${seconds} s.`, 'ok');
      if (current.done && !current.terminalSeen) {
        showMessage('The run ended before the master sent response.completed; the answer may be incomplete.', 'warn');
      } else if (!current.done) {
        showMessage('The connection to the bridge closed before the run finished.', 'warn');
      }
    }
    if (!current.quote && !text.trim() && !current.error && !current.stopRequested) {
      result.innerHTML = '<p class="rq-empty">No answer came back from the master.</p>';
    }
  }

  async function requestStop() {
    const current = run;
    if (!current || current.stopSent) return;
    if (!current.runId) {
      // No run ID yet: stop listening now; if the run line arrives first, handleLine retries.
      current.stopTimer = setTimeout(() => current.controller.abort(), 3000);
      return;
    }
    current.stopSent = true;
    clearTimeout(current.stopTimer);
    try {
      const digits = /^\d+$/.test(current.runId) ? current.runId : JSON.stringify(current.runId);
      const res = await fetch(`${base}/api/stop`, { method: 'POST', headers: headers(), body: `{"run_id": ${digits}}` });
      const data = parseJson(await res.text()) ?? {};
      if (data.stopped) {
        logLine(`stop run ${current.runId}: ok`, 'bad');
      } else {
        logLine(`stop run ${current.runId}: failed${data.error ? ` (${data.error})` : ''}`, 'bad');
        current.error = current.error ?? "Couldn't stop the run on the SuperLink (it may have finished already). Stopped listening.";
        current.controller.abort();
        return;
      }
    } catch (err) {
      logLine(`stop run ${current.runId}: ${err.message}`, 'bad');
    }
    current.stopTimer = setTimeout(() => current.controller.abort(), STOP_GRACE_MS);
  }

  function stop() {
    if (!run || run.stopRequested) return;
    run.stopRequested = true;
    stopButton.disabled = true;
    hideCacheOffer();
    if (run.mode === 'cache' || run.switchedToCache) {
      // A cache fetch or replay: nothing is running at Flower on our behalf, so just stop locally.
      setProgress('Stopping the replay…');
      run.controller.abort();
      return;
    }
    setProgress('Stopping the run…');
    requestStop();
  }

  async function start() {
    if (run) return;
    let items;
    try {
      items = typeof getItems === 'function' ? getItems() : [];
    } catch (err) {
      showMessage(`Couldn't read your build: ${err.message}`, 'error');
      return;
    }
    items = Array.isArray(items) ? items.filter((item) => item && item.product_id) : [];
    if (!items.length) {
      showMessage('Your build is empty. Pick some parts first, then ask the stores.', 'warn');
      return;
    }

    const mode = cacheInput.checked ? 'cache' : 'live';
    run = { mode, text: '', quote: null, quoteFromEvent: false, runId: null, started: Date.now(), controller: new AbortController() };
    showMessage('');
    showBanner('');
    hideCacheOffer();
    result.replaceChildren();
    renderAnswer('');
    logBody.replaceChildren();
    logCount.textContent = '';
    setRunning(true);
    const count = items.reduce((n, item) => n + qtyOf(item.qty), 0);

    const request = prompt.value.trim() || DEFAULT_REQUEST;
    // One string for both endpoints: the bridge keys its cache on exactly what /api/run was sent.
    const promptJson = JSON.stringify({ request, items });
    const current = run;
    const noteError = (err) => {
      if (err?.name === 'AbortError') {
        if (!current.stopRequested && !current.switchedToCache) current.error = current.error ?? 'Stopped listening to the run.';
      } else if (err instanceof TypeError) {
        current.error = current.error ?? `Can't reach the bridge (${err.message}). Start it with: python SuperGrid_RobotShop/bridge.py`;
      } else {
        current.error = current.error ?? err?.message ?? String(err);
      }
    };

    if (mode === 'cache') {
      setProgress(`Loading the cached run for ${plural(count, 'part')}…`);
      try {
        const cache = await fetchCache(promptJson, current.controller.signal);
        if (!cache) current.cacheMiss = true;
        else await replayCache(current, cache);
      } catch (err) {
        noteError(err);
      } finally {
        finish();
      }
      return;
    }

    setProgress(`Starting a run for ${plural(count, 'part')}…`);
    // In the background, learn whether a cached run exists (for "Show cached result now").
    fetchCache(promptJson)
      .then((cache) => {
        if (cache && cacheHasResult(cache)) {
          current.cache = cache;
          maybeOfferCache(current);
        }
      })
      .catch(() => {}); // no cache, old bridge, offline: just don't offer it
    try {
      const res = await fetch(`${base}/api/run`, {
        method: 'POST',
        headers: headers(),
        body: JSON.stringify({ prompt: promptJson, federation }),
        signal: current.controller.signal,
      });
      if (!res.ok) throw new Error(await errorFromResponse(res));
      await readStream(res);
    } catch (err) {
      noteError(err);
    }
    if (current.switchedToCache && run === current && !current.stopRequested) {
      try {
        await replayCache(current, current.cache, { liveStillRunning: true });
      } catch (err) {
        noteError(err);
      }
    }
    finish();
  }

  function setCacheMode(on) {
    cacheInput.checked = Boolean(on);
    writeCacheMode(cacheInput.checked);
  }

  buildButton.addEventListener('click', start);
  stopButton.addEventListener('click', stop);
  cacheNowButton.addEventListener('click', showCachedNow);
  cacheInput.addEventListener('change', () => writeCacheMode(cacheInput.checked));
  prompt.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
      e.preventDefault();
      start();
    }
  });

  return { root, run: start, stop, isRunning: () => Boolean(run), isCacheMode: () => cacheInput.checked, setCacheMode };
}
