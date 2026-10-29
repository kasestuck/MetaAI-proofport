/*
 * DOM + formatting helpers.
 *
 * SECURITY: every string coming from the backend (file names, scanner
 * messages, diffs, event details) is untrusted (handoff §9). `h()` only ever
 * sets text through text nodes / textContent. The single innerHTML use is
 * `icon()`, which renders constant SVG markup from the ICONS table below.
 */
(function (PP) {
  "use strict";

  /**
   * Create an element.
   *   h("div", { class: "card", onclick: fn, title: "x", dataset: { id: 1 } }, child, "text", [more])
   * Children: Node | string | number | null/undefined/false (skipped) | arrays (flattened).
   */
  function h(tag, attrs, ...children) {
    const el = document.createElement(tag);
    if (attrs) {
      for (const key of Object.keys(attrs)) {
        const value = attrs[key];
        if (value === null || value === undefined || value === false) continue;
        if (key === "class") el.className = value;
        else if (key === "text") el.textContent = String(value);
        else if (key === "dataset") Object.assign(el.dataset, value);
        else if (key === "style" && typeof value === "object") {
          for (const prop of Object.keys(value)) {
            if (prop.startsWith("--")) el.style.setProperty(prop, value[prop]); // CSS custom property
            else el.style[prop] = value[prop];
          }
        }
        else if (key.startsWith("on") && typeof value === "function") el.addEventListener(key.slice(2), value);
        else if (key in el && typeof value !== "string") el[key] = value;
        else el.setAttribute(key, value === true ? "" : String(value));
      }
    }
    append(el, children);
    return el;
  }

  function append(el, children) {
    for (const child of children) {
      if (child === null || child === undefined || child === false) continue;
      if (Array.isArray(child)) append(el, child);
      else if (child instanceof Node) el.appendChild(child);
      else el.appendChild(document.createTextNode(String(child)));
    }
  }

  // Constant, trusted SVG icons (24x24, stroke based).
  const P = 'fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"';
  const ICONS = {
    overview: `<svg viewBox="0 0 24 24" ${P}><rect x="3" y="3" width="7" height="9" rx="1.5"/><rect x="14" y="3" width="7" height="5" rx="1.5"/><rect x="14" y="12" width="7" height="9" rx="1.5"/><rect x="3" y="16" width="7" height="5" rx="1.5"/></svg>`,
    migration: `<svg viewBox="0 0 24 24" ${P}><path d="M4 7h11"/><path d="M12 3l4 4-4 4"/><path d="M20 17H9"/><path d="M12 13l-4 4 4 4"/></svg>`,
    security: `<svg viewBox="0 0 24 24" ${P}><path d="M12 3l7 3v5c0 4.5-3 8.5-7 10-4-1.5-7-5.5-7-10V6z"/><path d="M9 12l2 2 4-4"/></svg>`,
    compatibility: `<svg viewBox="0 0 24 24" ${P}><path d="M8 4v4"/><path d="M16 4v4"/><path d="M6 8h12v3a6 6 0 0 1-12 0z"/><path d="M12 17v4"/></svg>`,
    evidence: `<svg viewBox="0 0 24 24" ${P}><path d="M9 7h8"/><path d="M9 12h8"/><path d="M9 17h5"/><rect x="4" y="3" width="16" height="18" rx="2"/><path d="M6 7h.01M6 12h.01M6 17h.01"/></svg>`,
    check: `<svg viewBox="0 0 24 24" ${P} stroke-width="2.4"><path d="M5 12.5l4.5 4.5L19 7.5"/></svg>`,
    x: `<svg viewBox="0 0 24 24" ${P} stroke-width="2.4"><path d="M6 6l12 12M18 6L6 18"/></svg>`,
    dash: `<svg viewBox="0 0 24 24" ${P} stroke-width="2.4"><path d="M7 12h10"/></svg>`,
    alert: `<svg viewBox="0 0 24 24" ${P}><path d="M12 3l9.5 17h-19z"/><path d="M12 10v4.5"/><path d="M12 17.5h.01"/></svg>`,
    info: `<svg viewBox="0 0 24 24" ${P}><circle cx="12" cy="12" r="9"/><path d="M12 11v5.5"/><path d="M12 7.5h.01"/></svg>`,
    offline: `<svg viewBox="0 0 24 24" ${P}><path d="M3 3l18 18"/><path d="M8.5 16.5a5 5 0 0 1 7 0"/><path d="M5 12.5a10 10 0 0 1 4.2-2.4"/><path d="M14.8 10.1A10 10 0 0 1 19 12.5"/><path d="M12 20h.01"/></svg>`,
    play: `<svg viewBox="0 0 24 24" ${P}><path d="M7 4.5v15l12-7.5z"/></svg>`,
    download: `<svg viewBox="0 0 24 24" ${P}><path d="M12 4v11"/><path d="M7 10.5l5 5 5-5"/><path d="M5 20h14"/></svg>`,
    upload: `<svg viewBox="0 0 24 24" ${P}><path d="M12 20V9"/><path d="M7 13.5l5-5 5 5"/><path d="M5 4h14"/></svg>`,
    link: `<svg viewBox="0 0 24 24" ${P}><path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1"/><path d="M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1"/></svg>`,
    lock: `<svg viewBox="0 0 24 24" ${P}><rect x="5" y="11" width="14" height="10" rx="2"/><path d="M8 11V8a4 4 0 0 1 8 0v3"/></svg>`,
    hash: `<svg viewBox="0 0 24 24" ${P}><path d="M5 9h15M4 15h15M10 3L8 21M16 3l-2 18"/></svg>`,
    clock: `<svg viewBox="0 0 24 24" ${P}><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></svg>`,
    server: `<svg viewBox="0 0 24 24" ${P}><rect x="3" y="4" width="18" height="7" rx="1.5"/><rect x="3" y="13" width="18" height="7" rx="1.5"/><path d="M7 7.5h.01M7 16.5h.01"/></svg>`,
    box: `<svg viewBox="0 0 24 24" ${P}><path d="M21 8l-9-5-9 5 9 5z"/><path d="M3 8v8l9 5 9-5V8"/><path d="M12 13v8"/></svg>`,
    cpu: `<svg viewBox="0 0 24 24" ${P}><rect x="6" y="6" width="12" height="12" rx="2"/><path d="M9 2v3M15 2v3M9 19v3M15 19v3M2 9h3M2 15h3M19 9h3M19 15h3"/></svg>`,
    flask: `<svg viewBox="0 0 24 24" ${P}><path d="M9 3h6"/><path d="M10 3v6L4.5 18.5A1.7 1.7 0 0 0 6 21h12a1.7 1.7 0 0 0 1.5-2.5L14 9V3"/><path d="M7.5 15h9"/></svg>`,
    coin: `<svg viewBox="0 0 24 24" ${P}><circle cx="12" cy="12" r="9"/><path d="M14.5 9.5c-.5-1-1.5-1.5-2.5-1.5-1.5 0-2.5.8-2.5 2s1 1.7 2.5 2 2.5.8 2.5 2-1 2-2.5 2c-1 0-2-.5-2.5-1.5"/><path d="M12 6.5v1.5M12 16v1.5"/></svg>`,
    file: `<svg viewBox="0 0 24 24" ${P}><path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z"/><path d="M14 3v6h6"/></svg>`,
    trash: `<svg viewBox="0 0 24 24" ${P}><path d="M4 7h16"/><path d="M10 11v6M14 11v6"/><path d="M6 7l1 13h10l1-13"/><path d="M9 7V4h6v3"/></svg>`,
    refresh: `<svg viewBox="0 0 24 24" ${P}><path d="M20 11a8 8 0 0 0-14.6-4.5L4 8"/><path d="M4 4v4h4"/><path d="M4 13a8 8 0 0 0 14.6 4.5L20 16"/><path d="M20 20v-4h-4"/></svg>`,
  };

  function icon(name, cls) {
    const span = document.createElement("span");
    span.className = cls || "icon";
    span.setAttribute("aria-hidden", "true");
    span.style.display = "inline-flex";
    span.innerHTML = ICONS[name] || ""; // constant markup only
    return span;
  }

  // ---------- Formatting ----------
  const nf = new Intl.NumberFormat("en-US");

  const fmt = {
    int(n) { return Number.isFinite(n) ? nf.format(n) : "—"; },
    seconds(s) {
      if (!Number.isFinite(s)) return "—";
      if (s < 60) return s.toFixed(s < 10 ? 2 : 1) + " s";
      const m = Math.floor(s / 60);
      const r = Math.round(s - m * 60);
      return `${m}m ${String(r).padStart(2, "0")}s`;
    },
    usd(x) {
      if (!Number.isFinite(x)) return "—";
      if (x === 0) return "$0.00";
      return x < 0.01 ? "$" + x.toFixed(6) : "$" + x.toFixed(4);
    },
    shortHash(value, n) { return typeof value === "string" ? value.slice(0, n || 12) + "…" : "—"; },
    shortId(id) { return typeof id === "string" ? id.slice(0, 8) : "—"; },
    /** UTC ISO timestamp -> local HH:MM:SS.mmm (title attribute keeps the UTC value). */
    time(ts) {
      const d = new Date(ts);
      if (Number.isNaN(d.getTime())) return String(ts || "—");
      const pad = (v, l) => String(v).padStart(l || 2, "0");
      return `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}.${pad(d.getMilliseconds(), 3)}`;
    },
    dateTime(ts) {
      const d = new Date(ts);
      return Number.isNaN(d.getTime()) ? "—" : d.toLocaleString();
    },
    pyVersion(v) { return Array.isArray(v) ? v.join(".") : (v == null ? "—" : String(v)); },
    pct(part, total) { return total > 0 ? Math.round((part / total) * 100) : 0; },
  };

  // ---------- Small UI builders ----------
  function badge(text, tone, extra) {
    return h("span", { class: `badge badge--${tone || "muted"}${extra ? " " + extra : ""}` }, text);
  }

  function tag(text, tone) {
    return h("span", { class: `tag${tone ? " tag--" + tone : ""}` }, text);
  }

  // Last rendered width per progress key, so bars re-created by a re-render
  // start from their previous value and animate smoothly to the new one.
  const lastPct = new Map();

  /** Determinate progress bar; width animates via CSS transition. `key` keeps continuity across re-renders. */
  function progress(part, total, tone, small, key) {
    const fill = h("div", { class: "progress-fill" });
    const bar = h("div", {
      class: `progress${tone ? " progress--" + tone : ""}${small ? " progress--sm" : ""}`,
      role: "progressbar", "aria-valuemin": "0", "aria-valuemax": String(total || 0), "aria-valuenow": String(part || 0),
    }, fill);
    const pct = total > 0 ? Math.min(100, (part / total) * 100) : 0;
    const from = key && lastPct.has(key) ? lastPct.get(key) : 0;
    if (key) lastPct.set(key, pct);
    fill.style.width = from + "%";
    if (from !== pct) {
      // Two frames: the first commits the start width, the second triggers the transition.
      requestAnimationFrame(() => requestAnimationFrame(() => { fill.style.width = pct + "%"; }));
    }
    return bar;
  }

  /** Update an existing progress bar in place (keeps the CSS transition smooth). */
  function setProgress(bar, part, total) {
    const fill = bar.querySelector(".progress-fill");
    const pct = total > 0 ? Math.min(100, (part / total) * 100) : 0;
    fill.style.width = pct + "%";
    bar.setAttribute("aria-valuenow", String(part || 0));
    bar.setAttribute("aria-valuemax", String(total || 0));
  }

  function indeterminate(label) {
    return h("div", { class: "progress progress--indeterminate", role: "progressbar", "aria-label": label || "Working" }, h("div", { class: "progress-fill" }));
  }

  function empty(iconName, title, text, action) {
    return h("div", { class: "empty" }, icon(iconName || "info"), h("div", { class: "empty-title" }, title), text ? h("p", null, text) : null, action || null);
  }

  function card(opts, ...body) {
    const head = (opts.title || opts.actions) ? h("div", { class: "card-head" },
      h("div", null,
        opts.title ? h("div", { class: "card-title" }, opts.title, opts.titleExtra ? [" ", opts.titleExtra] : null) : null,
        opts.sub ? h("div", { class: "card-sub" }, opts.sub) : null),
      opts.actions ? h("div", { class: "row" }, opts.actions) : null) : null;
    return h("div", { class: `card${opts.flush ? " card-flush" : ""}${opts.class ? " " + opts.class : ""}` }, head, body);
  }

  function kv(pairs) {
    const dl = h("dl", { class: "kv" });
    for (const [k, v] of pairs) {
      if (v === undefined) continue;
      dl.appendChild(h("dt", null, k));
      dl.appendChild(h("dd", null, v === null ? h("span", { class: "dim" }, "—") : v));
    }
    return dl;
  }

  /** Render a unified diff as escaped text with +/- line coloring. */
  function diffBlock(text) {
    const pre = h("pre", { class: "code" });
    for (const line of String(text || "").split("\n")) {
      let cls = "diff-ctx";
      if (line.startsWith("@@")) cls = "diff-hunk";
      else if (line.startsWith("+") && !line.startsWith("+++")) cls = "diff-add";
      else if (line.startsWith("-") && !line.startsWith("---")) cls = "diff-del";
      pre.appendChild(h("span", { class: cls }, line || " "));
    }
    return pre;
  }

  function toast(title, message, tone) {
    const host = document.getElementById("toasts");
    if (!host) return;
    const iconName = tone === "ok" ? "check" : tone === "warn" ? "alert" : tone === "err" ? "alert" : "info";
    const el = h("div", { class: `toast toast--${tone || "info"}`, role: "status" },
      icon(iconName), h("div", null, h("div", { class: "toast-title" }, title), message ? h("div", { class: "muted" }, message) : null));
    host.appendChild(el);
    setTimeout(() => el.remove(), 6000);
  }

  const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

  PP.util = { h, icon, fmt, badge, tag, progress, setProgress, indeterminate, empty, card, kv, diffBlock, toast, sleep, ICONS };
})(window.PP);
