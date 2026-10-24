/**
 * Unit tests for the listener page (portal/static/js/listener-event.js).
 *
 * Run with: node tests/test_listener_event.js
 *
 * Loads the real module against a small fake DOM and stubbed WHEP client and
 * WebSockets, so the status badge and captions box can be checked without a
 * browser or media server.
 */
'use strict';

const path = require('path');
const { pathToFileURL } = require('url');

let passed = 0;
let failed = 0;

function assert(condition, message) {
  if (!condition) {
    console.error('  FAIL: ' + message);
    failed++;
  } else {
    console.log('  PASS: ' + message);
    passed++;
  }
}

// ── Fake DOM ─────────────────────────────────────────────────────────────

const elementsById = new Map();

class FakeElement {
  constructor(tagName) {
    this.tagName = tagName.toUpperCase();
    this.children = [];
    this.parentNode = null;
    this.style = {};
    this.dataset = {};
    this.attributes = {};
    this.className = '';
    this.disabled = false;
    this.listeners = {};
    this._id = '';
    this._text = '';
    this._value = '';
    this._selectedIndex = -1;
    this.scrollTop = 0;
  }

  get id() {
    return this._id;
  }

  set id(value) {
    this._id = value;
    elementsById.set(value, this);
  }

  get classList() {
    const el = this;
    const names = () => el.className.split(/\s+/).filter(Boolean);
    return {
      contains: (name) => names().includes(name),
      add: (...add) => {
        el.className = [...new Set([...names(), ...add])].join(' ');
      },
      remove: (...remove) => {
        el.className = names().filter((n) => !remove.includes(n)).join(' ');
      },
      toggle: (name) => {
        if (names().includes(name)) el.classList.remove(name);
        else el.classList.add(name);
      },
    };
  }

  get textContent() {
    return this._text + this.children.map((c) => c.textContent).join('');
  }

  set textContent(value) {
    this.children = [];
    this._text = String(value);
  }

  // Enough of an HTML parser for the flat markup listener-event.js writes.
  set innerHTML(html) {
    this.children = [];
    this._text = '';
    const tag = /<(\w+)(?: class="([^"]*)")?(?: value="([^"]*)")?>([^<]*)<\/\1>/g;
    let match;
    while ((match = tag.exec(html))) {
      const child = new FakeElement(match[1]);
      child.className = match[2] || '';
      if (match[3] !== undefined) child.value = match[3];
      child._text = match[4];
      this.appendChild(child);
    }
  }

  get firstChild() {
    return this.children[0] || null;
  }

  get firstElementChild() {
    return this.children[0] || null;
  }

  appendChild(child) {
    child.parentNode = this;
    this.children.push(child);
    if (this.tagName === 'SELECT' && this._selectedIndex === -1) this._selectedIndex = 0;
    return child;
  }

  removeChild(child) {
    this.children = this.children.filter((c) => c !== child);
    child.parentNode = null;
    return child;
  }

  querySelector(selector) {
    const name = selector.startsWith('.') ? selector.slice(1) : null;
    for (const child of this.children) {
      if (name && child.classList.contains(name)) return child;
      const found = child.querySelector(selector);
      if (found) return found;
    }
    return null;
  }

  setAttribute(name, value) {
    this.attributes[name] = String(value);
  }

  getAttribute(name) {
    return name in this.attributes ? this.attributes[name] : null;
  }

  removeAttribute(name) {
    delete this.attributes[name];
  }

  addEventListener(type, handler) {
    (this.listeners[type] = this.listeners[type] || []).push(handler);
  }

  dispatchEvent(event) {
    (this.listeners[event.type] || []).forEach((handler) => handler.call(this, event));
  }

  // <select> behaviour
  get options() {
    return this.children;
  }

  get selectedIndex() {
    return this.children.length ? this._selectedIndex : -1;
  }

  set selectedIndex(index) {
    this._selectedIndex = index;
  }

  get value() {
    if (this.tagName !== 'SELECT') return this._value;
    const opt = this.children[this.selectedIndex];
    return opt ? opt.value : '';
  }

  set value(value) {
    if (this.tagName !== 'SELECT') {
      this._value = value;
      return;
    }
    this._selectedIndex = this.children.findIndex((o) => o.value === String(value));
  }

  get text() {
    return this.textContent;
  }
}

const document = {
  getElementById: (id) => elementsById.get(id) || null,
  createElement: (tagName) => new FakeElement(tagName),
};

function make(tagName, id) {
  const el = new FakeElement(tagName);
  el.id = id;
  return el;
}

[
  'toggle-captions-btn',
  'share-event-btn',
  'share-event-status',
  'audio-player',
  'status',
  'caption-history',
  'caption-current',
  'waiting-text',
  'translation-lang-group',
  'tts-sync-group',
  'tts-sync-toggle',
  'captions-container',
].forEach((id) => make('div', id));
['room-select', 'language-select', 'caption-mode-select', 'translation-lang-select'].forEach((id) =>
  make('select', id),
);

const roomSelect = document.getElementById('room-select');
roomSelect.innerHTML = '<option value="">-- Select Room --</option><option value="1">Main Hall</option>';
const captionModeSelect = document.getElementById('caption-mode-select');
captionModeSelect.innerHTML =
  '<option value="original">Original</option><option value="translated">Translated</option>';
document.getElementById('waiting-text').className = 'absolute inset-0 flex';

// Captions box: each history row is 20px tall and 300px are visible.
const captionsBox = make('div', 'live-captions');
const historyBox = document.getElementById('caption-history');
Object.defineProperty(captionsBox, 'clientHeight', { get: () => 300 });
Object.defineProperty(captionsBox, 'scrollHeight', {
  get: () => Math.max(300, historyBox.children.length * 20),
});
let captionsScrollTop = 0;
Object.defineProperty(captionsBox, 'scrollTop', {
  get: () => captionsScrollTop,
  set: (value) => {
    captionsScrollTop = Math.max(0, Math.min(value, captionsBox.scrollHeight - captionsBox.clientHeight));
  },
});

const listenerData = make('script', 'listener-data');
listenerData.textContent = JSON.stringify({
  eventSlug: 'demo',
  shareUrl: 'https://example.test/listener/demo',
  rooms: [{ id: 1, floor_tts_enabled: false }],
  booths: [
    { id: 'floor_1', room_id: 1, language_code: 'floor', language_name: 'Floor Audio', whep_url: 'http://mtx/floor/whep', audio_delay_ms: 0 },
    { id: 2, room_id: 1, language_code: 'es', language_name: 'Spanish', whep_url: 'http://mtx/es/whep', audio_delay_ms: 0 },
  ],
});

// ── Stubbed browser APIs ─────────────────────────────────────────────────

let whepOpts = null;
const WhepListener = {
  start(opts) {
    whepOpts = opts;
  },
  stop() {
    if (whepOpts) whepOpts.onState({ peerConnection: 'closed', ice: 'closed', audioActive: false });
  },
};

const sockets = [];
class FakeWebSocket {
  constructor(url) {
    this.url = url;
    this.readyState = FakeWebSocket.OPEN;
    sockets.push(this);
  }
  send() {}
  close() {
    this.readyState = 3;
  }
}
FakeWebSocket.OPEN = 1;

function captionsSocket() {
  return sockets.filter((s) => s.url.includes('/ws/captions/')).pop();
}

let boothState = { ingest_status: 'disconnected' };
function fetch(url) {
  const body = url.includes('/audio-delay') ? { audio_delay_ms: 0 } : boothState;
  return Promise.resolve({ ok: true, json: () => Promise.resolve(body) });
}

Object.assign(globalThis, {
  document,
  WhepListener,
  WebSocket: FakeWebSocket,
  fetch,
  window: {
    location: { protocol: 'http:', host: 'portal.test' },
    setTimeout,
    setInterval: () => 0,
    addEventListener: () => {},
  },
});

// ── Helpers ──────────────────────────────────────────────────────────────

const languageSelect = document.getElementById('language-select');

function statusText() {
  return document.getElementById('status').textContent;
}

function choose(select, value) {
  select.value = value;
  select.dispatchEvent(new Event('change'));
}

function flush() {
  return new Promise((resolve) => setTimeout(resolve, 0));
}

async function run() {
  await import(pathToFileURL(path.join(__dirname, '..', 'portal', 'static', 'js', 'listener-event.js')).href);
  choose(roomSelect, '1');

  console.log('\n── Status badge (#985) ──');

  choose(languageSelect, 'http://mtx/floor/whep');
  assert(statusText() === 'Connecting...', 'floor audio shows Connecting... until audio plays, got "' + statusText() + '"');

  whepOpts.onState({ peerConnection: 'new', ice: 'new', audioActive: false });
  assert(statusText() === 'Reconnecting...', 'a failed WHEP request shows Reconnecting..., got "' + statusText() + '"');

  whepOpts.onState({ peerConnection: 'connected', ice: 'connected', audioActive: true });
  assert(statusText() === 'Live (WebRTC)', 'shows Live once audio is playing');

  choose(languageSelect, 'http://mtx/es/whep');
  assert(statusText() !== 'Live (WebRTC)', 'switching to a booth does not show Live before its state is known');
  await flush();
  await flush();
  assert(
    statusText() === 'Broadcast not live yet — waiting...',
    'a booth that is not live shows the waiting message, got "' + statusText() + '"',
  );

  console.log('\n' + passed + ' passed, ' + failed + ' failed');
  process.exit(failed > 0 ? 1 : 0);
}

run().catch((err) => {
  console.error(err);
  process.exit(1);
});
