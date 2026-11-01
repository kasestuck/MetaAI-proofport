/*
 * Independent, client-side re-verification of the evidence hash chain.
 *
 * Mirrors backend/core/evidence.py:
 *   entry_hash = sha256(prev_hash + json.dumps(payload_without_entry_hash,
 *                       sort_keys=True, separators=(",", ":"), ensure_ascii=False))
 *   prev_hash of seq 1 is 64 zeros; seq values are 1..N without gaps.
 *
 * This is a local consistency check of the data the browser received, not an
 * external signature (handoff §8). Requires WebCrypto (secure context:
 * http://127.0.0.1 / localhost qualify).
 */
(function (PP) {
  "use strict";

  const ZERO = "0".repeat(64);

  /** JSON with recursively sorted keys and no whitespace (Python sort_keys + compact separators). */
  function canonical(value) {
    if (Array.isArray(value)) return "[" + value.map(canonical).join(",") + "]";
    if (value && typeof value === "object") {
      return "{" + Object.keys(value).sort().map((k) => JSON.stringify(k) + ":" + canonical(value[k])).join(",") + "}";
    }
    return JSON.stringify(value);
  }

  async function sha256Hex(text) {
    const bytes = new TextEncoder().encode(text);
    const digest = await crypto.subtle.digest("SHA-256", bytes);
    return Array.from(new Uint8Array(digest), (b) => b.toString(16).padStart(2, "0")).join("");
  }

  /**
   * @returns {Promise<{status:"ok"|"broken"|"unavailable"|"empty", count:number, brokenAt?:number, reason?:string}>}
   */
  async function verifyChain(events) {
    if (!Array.isArray(events)) return { status: "broken", count: 0, reason: "Evidence must be an array." };
    const list = events.slice(); // Verify the supplied order; never repair corrupted evidence.
    if (!list.length) return { status: "empty", count: 0 };
    if (!(window.crypto && crypto.subtle)) {
      return { status: "unavailable", count: list.length, reason: "WebCrypto is unavailable (insecure context)." };
    }
    let previous = ZERO;
    for (let i = 0; i < list.length; i++) {
      const entry = list[i];
      if (!entry || typeof entry !== "object" || !Number.isSafeInteger(entry.seq)
          || typeof entry.prev_hash !== "string" || typeof entry.entry_hash !== "string") {
        return { status: "broken", count: list.length, reason: "Malformed evidence entry." };
      }
      if (entry.seq !== i + 1) return { status: "broken", count: list.length, brokenAt: entry.seq, reason: `Sequence gap: expected ${i + 1}, found ${entry.seq}.` };
      if (entry.prev_hash !== previous) return { status: "broken", count: list.length, brokenAt: entry.seq, reason: "prev_hash does not match the previous entry_hash." };
      const payload = {};
      for (const key of Object.keys(entry)) if (key !== "entry_hash") payload[key] = entry[key];
      const computed = await sha256Hex(entry.prev_hash + canonical(payload));
      if (computed !== entry.entry_hash) return { status: "broken", count: list.length, brokenAt: entry.seq, reason: "Recomputed SHA-256 differs from entry_hash." };
      previous = entry.entry_hash;
    }
    return { status: "ok", count: list.length };
  }

  PP.integrity = { verifyChain, canonical };
})(window.PP);
