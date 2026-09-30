import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import {
  cacheHasResult,
  cachedBannerText,
  escapeHtml,
  extractQuoteBlock,
  formatMoney,
  logEntryFor,
  normalizeCachedRun,
  parseNdjsonChunks,
  progressFrom,
  renderMarkdown,
  renderQuoteHtml,
  replayDelays,
  summarizeRunLines,
} from '../src/quote.js';

const fixture = readFileSync(new URL('./fixtures/run.ndjson', import.meta.url), 'utf8');
const cents = (x) => Math.round(Number(x) * 100);

const sampleQuote = (overrides = {}) => ({
  request: 'Build this robot for me',
  lines: [
    { product_id: 'pololu-3500', name: 'Romi Chassis Kit - Black', sku: '3500', qty: 1, unit_price: 39.95, currency: 'USD', subtotal: 39.95, url: 'https://www.pololu.com/product/3500', store_id: 'pololu', store_name: 'Pololu Robotics & Electronics', node_id: '7' },
    { product_id: 'adafruit-3777', name: '<script>alert(1)</script> TT motor', sku: '3777', qty: 2, unit_price: 2.95, currency: 'USD', subtotal: 5.9, url: 'javascript:alert(1)', store_id: 'adafruit', store_name: 'Adafruit Industries', node_id: '8' },
  ],
  unquoted: [
    { product_id: 'niryo-ned2', name: 'Ned2 arm', qty: 1, store_id: 'niryo', code: 'no_store', reason: 'no store sells it' },
  ],
  stores: [
    { store_id: 'pololu', store_name: 'Pololu Robotics & Electronics', node_id: '7', subtotal: 39.95, currency: 'USD', items: 1 },
    { store_id: 'adafruit', store_name: 'Adafruit Industries', node_id: '8', subtotal: 5.9, currency: 'USD', items: 2 },
  ],
  totals: { USD: 45.85 },
  nodes: { asked: 12, targeted: false, stores_replied: 8, no_catalog: 4, errors: [], timed_out: 0 },
  ...overrides,
});

// ------------------------------------------------------------------ NDJSON parsing

test('parseNdjsonChunks joins a line split across chunks and skips blank/garbage lines', () => {
  const a = parseNdjsonChunks('{"kind":"run","run_id":5}\n{"kind":"ev', '');
  assert.equal(a.lines.length, 1);
  assert.equal(a.lines[0].kind, 'run');
  assert.equal(a.carry, '{"kind":"ev');

  const b = parseNdjsonChunks('ent","type":"x","payload":{}}\n\n   \nnot json at all\n[1,2]\n{"kind":"done","terminal_seen":true}\n', a.carry);
  assert.deepEqual(b.lines.map((l) => l.kind), ['event', 'done']);
  assert.equal(b.lines[0].type, 'x');
  assert.equal(b.carry, '');
});

test('parseNdjsonChunks keeps an unterminated last line until flushed', () => {
  const a = parseNdjsonChunks('{"kind":"done","terminal_seen":false}', '');
  assert.equal(a.lines.length, 0);
  const b = parseNdjsonChunks('\n', a.carry);
  assert.equal(b.lines.length, 1);
  assert.equal(b.lines[0].terminal_seen, false);
});

test('parseNdjsonChunks keeps the exact digits of a 64-bit run_id', () => {
  const { lines } = parseNdjsonChunks('{"kind": "run", "run_id": 16140901064495857664, "series_id": 1}\n');
  assert.equal(lines[0].run_id_str, '16140901064495857664');
});

// ------------------------------------------------------------------ progress

test('progressFrom maps the three Grid calls, the progress event and the quote event', () => {
  const call = (name, args) => ({ kind: 'event', type: 'function_call', payload: { type: 'function_call', call_id: `${name}-1`, name, arguments: JSON.stringify(args) } });
  assert.equal(progressFrom(call('get_nodes', { sample_size: null })), 'Finding store nodes…');
  const messages = [1, 2, 3].map((i) => ({ dst_node_id: String(i), payload: '{}', reply_to_message_id: null }));
  assert.equal(progressFrom(call('push_messages', { messages })), 'Asking 3 stores…');
  assert.equal(progressFrom(call('push_messages', { messages: messages.slice(0, 1) })), 'Asking 1 store…');
  assert.equal(progressFrom({ kind: 'event', type: 'function_call', payload: { name: 'push_messages', arguments: 'not json' } }), 'Asking the stores…');
  assert.equal(progressFrom(call('pull_messages', { message_ids: ['a'], timeout: 60 })), 'Collecting quotes…');
  assert.equal(
    progressFrom({ kind: 'event', type: 'robotshop.progress', payload: { type: 'robotshop.progress', replied: 5, expected: 8, stores: ['pololu'] } }),
    '5 of 8 stores answered…',
  );
  assert.equal(progressFrom({ kind: 'event', type: 'robotshop.quote', payload: { type: 'robotshop.quote', quote: {} } }), 'Writing the answer…');
  assert.equal(progressFrom({ kind: 'event', type: 'function_call_output', payload: { output: '{}' } }), null);
  assert.equal(progressFrom({ kind: 'event', type: 'response.output_text.delta', payload: { delta: 'hi' } }), null);
  assert.equal(progressFrom({ kind: 'done', terminal_seen: true }), null);
  assert.equal(progressFrom(null), null);
});

test('the run log names the stores from robotshop.progress', () => {
  const [text] = logEntryFor('robotshop.progress', { replied: 2, expected: 12, stores: ['pololu', 'adafruit'] });
  assert.match(text, /2 of 12/);
  assert.match(text, /pololu, adafruit/);
});

// ------------------------------------------------------------------ quote rendering

test('renderQuoteHtml escapes names, shows totals, store groups and the unquoted list', () => {
  const html = renderQuoteHtml(sampleQuote());
  assert.ok(!html.includes('<script'), 'raw <script> must not appear');
  assert.ok(html.includes('&lt;script&gt;'), 'the name is shown escaped');
  assert.ok(!html.includes('javascript:'), 'non-http URLs are not linked');
  assert.ok(html.includes('$45.85'), 'grand total');
  assert.ok(html.includes('$39.95'), 'Pololu subtotal');
  assert.ok(html.includes('$5.90'), 'Adafruit line subtotal');
  assert.ok(html.includes('$2.95 each'), 'unit price');
  assert.ok(html.includes('Pololu Robotics &amp; Electronics'), 'store name escaped');
  assert.ok(html.includes('href="https://www.pololu.com/product/3500" target="_blank" rel="noopener noreferrer"'));
  assert.ok(html.includes('No store sells it'));
  assert.ok(html.includes('Ned2 arm'));
  assert.ok(html.includes('8 store nodes answered (12 nodes asked, 4 without a catalogue)'));
  assert.ok(!/class="[^"]*total/i.test(html) && !/id="/.test(html), 'no "total" classes or ids (Playwright counts #total)');
  assert.ok(!html.includes('part-card'));
});

test('renderQuoteHtml: targeted status, errors, timeouts and not_stocked reasons', () => {
  const html = renderQuoteHtml(sampleQuote({
    unquoted: [
      { product_id: 'niryo-ned2', name: 'Ned2 arm', qty: 1, store_id: 'niryo', code: 'no_store', reason: 'no store sells it' },
      { product_id: 'pololu-9999', name: 'Motor <b>driver</b>', qty: 2, store_id: 'pololu', code: 'not_stocked', reason: "Pololu doesn't stock it" },
    ],
    nodes: { asked: 8, targeted: true, stores_replied: 6, no_catalog: 0, errors: [{ node_id: '42', message: 'bad <reply>' }], timed_out: 1 },
  }));
  assert.ok(html.includes('6 of 8 store nodes answered'));
  assert.ok(html.includes('1 error'));
  assert.ok(html.includes('1 timed out'));
  assert.ok(html.includes('node 42: bad &lt;reply&gt;'));
  assert.ok(html.includes('Pololu doesn&#39;t stock it'));
  assert.ok(html.includes('Motor &lt;b&gt;driver&lt;/b&gt;'));
  assert.ok(html.includes('No store sells it'));
});

test('renderQuoteHtml copes with an empty or partial quote', () => {
  assert.match(renderQuoteHtml(null), /No quote came back/);
  const html = renderQuoteHtml({ lines: [], unquoted: [], stores: [], totals: {}, nodes: { asked: 4, stores_replied: 0, no_catalog: 4, errors: [], timed_out: 0 } });
  assert.match(html, /No store quoted any of these parts/);
  assert.match(html, /0 store nodes answered \(4 nodes asked, 4 without a catalogue\)/);
  // totals missing: recomputed from the lines in cents (3 × 10.95 = 32.85 exactly)
  const recomputed = renderQuoteHtml({ lines: [{ name: 'x', qty: 3, unit_price: 10.95, currency: 'USD', store_id: 's', store_name: 'S' }] });
  assert.ok(recomputed.includes('$32.85'));
});

test('formatMoney falls back for an unknown currency code', () => {
  assert.equal(formatMoney(45.85, 'USD'), '$45.85');
  assert.equal(formatMoney(1.5, 'NOTACODE'), '1.50 NOTACODE');
  assert.equal(formatMoney(null, 'USD'), '—');
});

// ------------------------------------------------------------------ answer text

test('extractQuoteBlock strips the fenced block and parses Q', () => {
  const Q = sampleQuote();
  const text = `Your robot costs **$45.85**.\n\n\`\`\`robotshop-quote\n${JSON.stringify(Q)}\n\`\`\``;
  const out = extractQuoteBlock(text);
  assert.equal(out.text, 'Your robot costs **$45.85**.');
  assert.deepEqual(out.quote, Q);

  const none = extractQuoteBlock('Just text.');
  assert.equal(none.text, 'Just text.');
  assert.equal(none.quote, null);

  const broken = extractQuoteBlock('Hi\n\n```robotshop-quote\n{not json\n```');
  assert.equal(broken.text, 'Hi');
  assert.equal(broken.quote, null);
});

test('extractQuoteBlock hides a half-arrived block while streaming', () => {
  assert.equal(extractQuoteBlock('Hi\n\n```robotshop-quote\n{"lines":[', { streaming: true }).text, 'Hi');
  assert.equal(extractQuoteBlock('Hi\n\n```robots', { streaming: true }).text, 'Hi');
  assert.equal(extractQuoteBlock('Hi `x`', { streaming: true }).text, 'Hi `x`');
});

test('renderMarkdown escapes first, then renders bold, code, bullets and breaks', () => {
  const html = renderMarkdown('Total **$45.85** for `pololu-3500`\n<img src=x onerror=alert(1)>\n\n- one\n- **two**');
  assert.ok(!html.includes('<img'));
  assert.ok(html.includes('&lt;img src=x onerror=alert(1)&gt;'));
  assert.ok(html.includes('<strong>$45.85</strong>'));
  assert.ok(html.includes('<code>pololu-3500</code>'));
  assert.ok(html.includes('<br>'));
  assert.ok(html.includes('<ul><li>one</li><li><strong>two</strong></li></ul>'));
  assert.ok(!renderMarkdown('[x](javascript:alert(1))').includes('href'));
  assert.equal(escapeHtml(`<a href="x">'&`), '&lt;a href=&quot;x&quot;&gt;&#39;&amp;');
});

// ------------------------------------------------------------------ fixture replay

test('replaying run.ndjson in small chunks yields the quote event, progress and a clean answer', () => {
  const lines = [];
  let carry = '';
  for (let i = 0; i < fixture.length; i += 97) {
    const parsed = parseNdjsonChunks(fixture.slice(i, i + 97), carry);
    carry = parsed.carry;
    lines.push(...parsed.lines);
  }
  lines.push(...parseNdjsonChunks('\n', carry).lines);
  assert.equal(lines.length, fixture.trim().split('\n').length, 'every fixture line parses');

  assert.equal(lines[0].kind, 'run');
  assert.equal(lines[0].run_id_str, '16140901064495857664');
  assert.deepEqual(lines.at(-1), { kind: 'done', terminal_seen: true });

  const steps = lines.map(progressFrom).filter(Boolean);
  assert.deepEqual(steps, [
    'Finding store nodes…',
    'Asking 12 stores…',
    'Collecting quotes…',
    '7 of 12 stores answered…',
    'Collecting quotes…',
    '12 of 12 stores answered…',
    'Writing the answer…',
  ]);

  const quoteEvent = lines.find((l) => l.kind === 'event' && l.type === 'robotshop.quote');
  assert.ok(quoteEvent, 'robotshop.quote event present');
  const Q = quoteEvent.payload.quote;
  const sum = Q.lines.reduce((n, l) => n + cents(l.subtotal), 0);
  assert.equal(sum, cents(Q.totals.USD));
  assert.equal(Q.totals.USD, 45.85);
  assert.equal(Q.lines.length, 2);
  assert.deepEqual(Q.unquoted.map((u) => u.product_id), ['niryo-ned2']);
  assert.deepEqual(Q.nodes, { asked: 12, targeted: false, stores_replied: 8, no_catalog: 4, errors: [], timed_out: 0 });

  const text = lines
    .filter((l) => l.kind === 'event' && l.type === 'response.output_text.delta')
    .map((l) => l.payload.delta)
    .join('');
  const answer = extractQuoteBlock(text);
  assert.ok(!answer.text.includes('robotshop-quote'));
  assert.ok(answer.text.includes('$45.85'));
  assert.deepEqual(answer.quote, Q, 'the fallback block matches the event');

  const html = renderQuoteHtml(Q);
  assert.ok(html.includes('$45.85'));
  assert.ok(html.includes('DC Gearbox Motor - &quot;TT Motor&quot;'));
});

// ------------------------------------------------------------------ cache mode

// What POST /api/cache returns: the bridge's lines after a JSON round trip (so the 64-bit run_id on
// the run line is a rounded number) plus the exact run_id as a digits string.
const cacheBody = (overrides = {}) => ({
  key: 'abc123',
  saved_at: '2026-09-29T15:04:05.123456+00:00',
  run_id: '16140901064495857664',
  request: 'Build this robot for me',
  items: [{ product_id: 'pololu-3500', qty: 1 }],
  lines: fixture.trim().split('\n').map((line) => JSON.parse(line)),
  ...overrides,
});

test('cachedBannerText names the cached run and its time, and says how to go live', () => {
  const cache = normalizeCachedRun(cacheBody());
  const text = cachedBannerText(cache);
  assert.match(text, /^Cached result/);
  assert.ok(text.includes('16140901064495857664'), 'exact run id');
  assert.ok(!text.includes('Invalid Date'), "Python's 6-digit fraction still parses");
  assert.match(text, /Turn off Cache mode for a live run\./);

  const live = cachedBannerText(cache, { liveStillRunning: true });
  assert.match(live, /^Cached result/);
  assert.ok(live.includes('16140901064495857664'));
  assert.match(live, /The live run is still finishing at Flower in the background\./);

  assert.match(cachedBannerText({ run_id: '42', saved_at: 'garbage' }), /run 42 at an earlier time/);
});

test('a cached run restores the exact run_id and replays to the same quote and answer', () => {
  const body = cacheBody();
  assert.notEqual(String(body.lines[0].run_id), '16140901064495857664', 'JSON.parse rounds the 64-bit id');
  const cache = normalizeCachedRun(body);
  assert.equal(cache.runId, '16140901064495857664');
  assert.equal(cache.lines[0].run_id_str, '16140901064495857664');
  assert.equal(cache.lines.length, fixture.trim().split('\n').length);

  const run = summarizeRunLines(cache.lines);
  assert.equal(run.runId, '16140901064495857664');
  assert.ok(run.quoteFromEvent);
  assert.equal(run.quote.totals.USD, 45.85);
  assert.equal(run.quote.lines.length, 2);
  assert.ok(run.done && run.terminalSeen && run.completed);
  assert.ok(run.answer.includes('$45.85') && !run.answer.includes('robotshop-quote'));
  assert.equal(run.steps.at(-1), 'Writing the answer…');
  assert.ok(renderQuoteHtml(run.quote).includes('$45.85'));
  assert.ok(cacheHasResult(cache));

  // Without the robotshop.quote event the quote still comes from the fenced block in the text.
  const noEvent = summarizeRunLines(cache.lines.filter((l) => l.type !== 'robotshop.quote'));
  assert.equal(noEvent.quoteFromEvent, false);
  assert.equal(noEvent.quote.totals.USD, 45.85);

  assert.equal(normalizeCachedRun({ error: 'no cached run for this build' }), null);
  assert.equal(normalizeCachedRun(cacheBody({ lines: [] })), null);
  assert.equal(normalizeCachedRun(null), null);
  assert.equal(cacheHasResult(normalizeCachedRun(cacheBody({ lines: [{ kind: 'run', run_id: 1 }, { kind: 'done', terminal_seen: true }] }))), false);
});

test('replayDelays paces lines, speeds up text deltas and caps the whole replay', () => {
  const lines = normalizeCachedRun(cacheBody()).lines;
  const delays = replayDelays(lines);
  assert.equal(delays.length, lines.length);
  assert.equal(delays[0], 0);
  const deltaAt = lines.findIndex((l, i) => i > 0 && l.type === 'response.output_text.delta');
  const callAt = lines.findIndex((l, i) => i > 0 && l.type === 'function_call');
  assert.ok(deltaAt > 0 && callAt > 0);
  assert.ok(delays[deltaAt] < delays[callAt], 'text deltas replay faster');
  assert.equal(delays[callAt], 120);

  const many = [{ kind: 'run' }, ...Array.from({ length: 2000 }, () => ({ kind: 'event', type: 'response.output_text.delta', payload: { delta: 'x' } }))];
  const capped = replayDelays(many, { maxTotalMs: 8000 });
  assert.ok(capped.reduce((n, d) => n + d, 0) <= 8000 + many.length, 'about 8 s at most');
  assert.deepEqual(replayDelays([]), []);
});
