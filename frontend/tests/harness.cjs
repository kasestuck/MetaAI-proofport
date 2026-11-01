const vm = require("node:vm");
const fs = require("node:fs");
const path = require("node:path");
const { webcrypto } = require("node:crypto");
const fixtures = require("./contract-fixtures.cjs");
const root = path.resolve(__dirname, "..");

function response(body, status = 200, type = "application/json") {
  return { status, ok: status >= 200 && status < 300, statusText: "", headers: { get: () => type },
    json: async () => fixtures.copy(body) };
}
function deferred() {
  let resolve, reject;
  const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}
const flush = async () => { for (let i = 0; i < 8; i++) await new Promise(setImmediate); };
async function until(condition) {
  for (let i = 0; i < 100; i++) { if (condition()) return; await flush(); }
  throw new Error("Condition did not become true");
}

// Small DOM adapter for component wiring tests. This is not browser layout QA.
class Element {
  constructor(tag = "div") {
    this.tagName = tag.toUpperCase(); this.children = []; this.dataset = {};
    this.style = { setProperty(k, v) { this[k] = v; } }; this.attributes = {};
    this.events = {}; this.value = ""; this.hidden = false; this.disabled = false;
    this.className = ""; this._text = ""; this.parentNode = null;
  }
  setAttribute(k, v) { this.attributes[k] = String(v); if (k === "value") this.value = String(v); if (k === "id") this.id = v; }
  getAttribute(k) { return this.attributes[k] ?? null; }
  removeAttribute(k) { delete this.attributes[k]; }
  addEventListener(k, fn) { (this.events[k] ||= []).push(fn); }
  dispatch(k) { for (const fn of this.events[k] || []) fn({ target: this, preventDefault() {} }); }
  appendChild(child) { child.parentNode = this; this.children.push(child); return child; }
  replaceChildren(...children) { this.children = []; this._text = ""; for (const child of children) this.appendChild(child instanceof Element ? child : new Text(String(child))); }
  set textContent(s) { this.children = []; this._text = String(s); }
  get textContent() { return this._text + this.children.map((c) => c.textContent).join(""); }
  remove() { if (this.parentNode) this.parentNode.children = this.parentNode.children.filter((c) => c !== this); }
  matches(selector) {
    if (selector.startsWith("#")) return this.id === selector.slice(1);
    const match = /^(\w+)?(?:\.([\w-]+))?(?:\[([\w-]+)(?:="([^"]*)")?\])?$/.exec(selector);
    if (!match) return false;
    const [, tag, cls, attr, value] = match;
    const attribute = attr && (attr.startsWith("data-") ? this.dataset[attr.slice(5).replace(/-([a-z])/g, (_, c) => c.toUpperCase())] : this.getAttribute(attr));
    return (!tag || this.tagName === tag.toUpperCase()) && (!cls || this.className.split(" ").includes(cls))
      && (!attr || (value === undefined ? attribute != null : attribute === value));
  }
  querySelectorAll(selector) { return this.children.flatMap((c) => [...(c.matches(selector) ? [c] : []), ...c.querySelectorAll(selector)]); }
  querySelector(selector) { return this.querySelectorAll(selector)[0] || null; }
}
class Text extends Element { constructor(text) { super("#text"); this._text = text; } }

function harness(handler, saved = {}) {
  const calls = [], sleeps = [], storage = new Map(Object.entries(saved));
  const document = new Element("document");
  Object.assign(document, { createElement: (tag) => new Element(tag), createTextNode: (s) => new Text(s),
    createComment: (s) => new Text(s), getElementById: (id) => document.querySelector("#" + id), readyState: "loading" });
  const window = { PP: {}, crypto: webcrypto, confirm: () => true, addEventListener() {} };
  const context = vm.createContext({ window, document, Node: Element, crypto: webcrypto, TextEncoder, AbortController,
    setTimeout, clearTimeout, queueMicrotask, requestAnimationFrame: (callback) => callback(), console, Intl, Date, URL, location: { origin: "http://127.0.0.1:8000", hash: "#/migration" },
    localStorage: { getItem: (k) => storage.get(k) || null, setItem: (k, v) => storage.set(k, v), removeItem: (k) => storage.delete(k) },
    fetch: async (url, options) => {
      if (!url.startsWith("/api/")) throw new Error("Forbidden external request: " + url);
      const call = { url, ...options, payload: options.body ? JSON.parse(options.body) : null };
      calls.push(call);
      const reply = await handler(call, calls);
      if (reply === undefined) throw new Error("Unmocked fetch: " + url);
      return reply;
    },
  });
  function load(file) { vm.runInContext(fs.readFileSync(path.join(root, file), "utf8"), context, { filename: file }); }
  for (const name of ["config", "util", "api", "labels", "integrity", "store", "control", "control-form"]) load("js/" + name + ".js");
  const PP = window.PP;
  PP.util.sleep = () => new Promise((resolve) => sleeps.push(resolve));
  PP.util.toast = () => {};
  return { PP, calls, sleeps, storage, document, load, tick: async () => { sleeps.shift()?.(); await flush(); },
    cleanup: () => PP.store.clearRun() };
}
function defaultReply(call) {
  if (call.url === "/api/v1/capabilities") return response(fixtures.capabilities);
  if (call.url === "/api/v1/projects") return response(fixtures.projects);
  if (call.url === "/api/v1/runs/preflight") return response({ can_start: true, errors: [], parameters: { ...fixtures.parameters, ...call.payload } });
  if (call.url === "/api/v1/runs" && call.method === "POST") return response({ run_id: "run-one" }, 202);
  if (call.url === "/api/v1/runs/run-one") return response(fixtures.details("running"));
  if (call.url.includes("/events?since=")) return response([]);
  if (call.url.endsWith("/report?format=json")) return response(fixtures.report());
  if (call.url === "/api/health") return response({ ok: true, docker: true, llm_mode: "mock" });
}
module.exports = { harness, response, deferred, flush, until, defaultReply, Element };
