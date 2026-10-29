/*
 * Thin client for the five existing backend endpoints (FRONTEND_HANDOFF.md §3).
 * Do not add routes or request fields here that the backend does not
 * implement: POST /api/runs rejects anything except source_path and
 * max_iterations with HTTP 422.
 *
 * Every failure is normalised to ApiError:
 *   kind "network" – backend unreachable / timeout (status 0)
 *   kind "http"    – non-2xx with the backend envelope {error:{code,message}} when present
 *   kind "parse"   – unexpected Content-Type or malformed JSON
 */
(function (PP) {
  "use strict";

  class ApiError extends Error {
    constructor(kind, status, code, message) {
      super(message);
      this.name = "ApiError";
      this.kind = kind;
      this.status = status;
      this.code = code;
    }
  }

  function url(path) {
    return (PP.config.apiBase || "") + path;
  }

  async function request(path, options) {
    const opts = options || {};
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), opts.timeoutMs || PP.config.requestTimeoutMs);
    let response;
    try {
      response = await fetch(url(path), {
        method: opts.method || "GET",
        headers: Object.assign({ Accept: "application/json" }, opts.body ? { "Content-Type": "application/json" } : {}),
        body: opts.body ? JSON.stringify(opts.body) : undefined,
        cache: "no-store",
        signal: controller.signal,
      });
    } catch (err) {
      const timedOut = err && err.name === "AbortError";
      throw new ApiError("network", 0, timedOut ? "timeout" : "network_error",
        timedOut ? "The backend did not respond in time." : "The backend is unreachable.");
    } finally {
      clearTimeout(timeout);
    }

    const type = response.headers.get("content-type") || "";
    let body = null;
    if (type.includes("application/json")) {
      try {
        body = await response.json();
      } catch (_) {
        throw new ApiError("parse", response.status, "invalid_json", "The backend returned malformed JSON.");
      }
    }

    if (!response.ok) {
      const envelope = body && typeof body === "object" && body.error && typeof body.error === "object" ? body.error : null;
      throw new ApiError("http", response.status,
        envelope && envelope.code ? String(envelope.code) : "http_" + response.status,
        envelope && envelope.message ? String(envelope.message) : `HTTP ${response.status} ${response.statusText || ""}`.trim());
    }
    if (body === null) {
      throw new ApiError("parse", response.status, "unexpected_content_type", `Expected JSON, received "${type || "unknown"}".`);
    }
    return body;
  }

  const api = {
    ApiError,

    /** GET /api/health -> {ok, docker, llm_mode} */
    health() {
      return request("/api/health", { timeoutMs: 4000 });
    },

    /** POST /api/runs -> {run_id}. Not idempotent: never auto-retry. */
    startRun(sourcePath, maxIterations) {
      const body = { source_path: sourcePath };
      if (Number.isInteger(maxIterations)) body.max_iterations = maxIterations;
      return request("/api/runs", { method: "POST", body });
    },

    /** GET /api/runs/{id} -> RunState (HTTP 200 even when status is "failed"). */
    getRun(id) {
      return request("/api/runs/" + encodeURIComponent(id));
    },

    /** GET /api/runs/{id}/events?since=N -> Event[] with seq > N. */
    getEvents(id, since) {
      return request(`/api/runs/${encodeURIComponent(id)}/events?since=${Math.max(0, since | 0)}`);
    },

    /** GET /api/runs/{id}/report?format=json -> full report (409 run_not_finished before terminal status). */
    getReport(id) {
      return request(`/api/runs/${encodeURIComponent(id)}/report?format=json`, { timeoutMs: PP.config.reportTimeoutMs });
    },

    /** Download URL for the existing report route (served with Content-Disposition: attachment). */
    reportUrl(id, format) {
      return url(`/api/runs/${encodeURIComponent(id)}/report?format=${format === "json" ? "json" : "html"}`);
    },
  };

  PP.api = api;
})(window.PP);
