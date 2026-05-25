// Browser OTLP tracing for the AMS frontend.
//
// CRITICAL — credentials in the public bundle: VITE_* env vars are inlined
// into the JavaScript bundle at build time and are visible to every browser
// user. Do NOT add a VITE_OTEL_HEADERS / VITE_OTEL_AUTH build arg or
// otherwise plumb an Authorization header through import.meta.env. Browser
// OTLP must target either:
//   - a CORS-friendly, unauthenticated public endpoint; or
//   - a backend-proxied OTLP relay that vends short-lived per-session tokens.
// See docs/plans/observability-prod-migration-plan.md for the production
// wiring.

const DEFAULT_ENDPOINT = "http://localhost:4318/v1/traces";
const DEFAULT_SERVICE_NAME = "ams-frontend";

export interface InitObservabilityOptions {
  enabled?: boolean;
  endpoint?: string;
  serviceName?: string;
  propagateTraceHeaderCorsUrls?: (string | RegExp)[];
}

let initialized = false;

export async function initObservability(
  options: InitObservabilityOptions = {},
): Promise<boolean> {
  const enabled = options.enabled ?? readEnvFlag("VITE_OTEL_ENABLED");
  if (!enabled) return false;
  if (initialized) return false;

  // Dynamic imports keep the OTel browser SDK out of the bundle when tracing
  // is disabled (the default in production). As top-level static imports the
  // ~80–120 KB gzipped SDK would ship to every user regardless of the flag.
  try {
    const [
      { getWebAutoInstrumentations },
      { OTLPTraceExporter },
      { registerInstrumentations },
      { resourceFromAttributes },
      { BatchSpanProcessor, WebTracerProvider },
      { ATTR_SERVICE_NAME },
    ] = await Promise.all([
      import("@opentelemetry/auto-instrumentations-web"),
      import("@opentelemetry/exporter-trace-otlp-http"),
      import("@opentelemetry/instrumentation"),
      import("@opentelemetry/resources"),
      import("@opentelemetry/sdk-trace-web"),
      import("@opentelemetry/semantic-conventions"),
    ]);

    const endpoint =
      options.endpoint ?? readEnvString("VITE_OTEL_ENDPOINT") ?? DEFAULT_ENDPOINT;
    const serviceName = options.serviceName ?? DEFAULT_SERVICE_NAME;
    const propagateTraceHeaderCorsUrls =
      options.propagateTraceHeaderCorsUrls ?? derivePropagateUrlsFromEnv();

    const exporter = new OTLPTraceExporter({ url: endpoint });
    const resource = resourceFromAttributes({ [ATTR_SERVICE_NAME]: serviceName });
    const provider = new WebTracerProvider({
      resource,
      spanProcessors: [new BatchSpanProcessor(exporter)],
    });
    provider.register();

    registerInstrumentations({
      instrumentations: getWebAutoInstrumentations({
        "@opentelemetry/instrumentation-xml-http-request": { enabled: false },
        "@opentelemetry/instrumentation-fetch": {
          propagateTraceHeaderCorsUrls,
        },
      }),
    });

    initialized = true;
    return true;
  } catch (err) {
    // Telemetry must never crash the app. Log loudly so a dev notices the
    // misconfig (typo'd endpoint, missing peer dep, HMR re-init) but let
    // React render normally. initialized stays false so a later retry can
    // try again from a clean state.
    //
    // The browser-side OTLP SDK has no way to report its own init failure
    // back to Grafana Cloud (CORS, no auth, no fallback channel). Without
    // a backend beacon, a misconfigured prod build silently disables
    // tracing for 100% of users — indistinguishable from
    // VITE_OTEL_ENABLED=false from the operator's view. Fire a
    // navigator.sendBeacon so the backend's
    // ams_frontend_observability_init_failures_total counter ticks and
    // an alert can catch the regression in the next deploy. Best-effort:
    // older browsers without sendBeacon (none in our supported matrix
    // today) silently degrade to console-only.
    reportInitFailure(err);
    console.warn("[observability] init failed; tracing disabled", err);
    return false;
  }
}

const _CLIENT_ERROR_BEACON_URL = "/api/v1/observability/client-error";
const _MAX_MESSAGE_LEN = 500;

function reportInitFailure(err: unknown): void {
  // Bail when the runtime doesn't support sendBeacon — the page-unload
  // safety guarantee that motivated sendBeacon is the reason we use it
  // here too (a regular fetch with no `await` can be cancelled before the
  // browser flushes the request). Older browsers fall back to silent
  // console-only diagnostics.
  if (typeof navigator === "undefined" || typeof navigator.sendBeacon !== "function") {
    return;
  }
  const message =
    err instanceof Error
      ? err.message.slice(0, _MAX_MESSAGE_LEN)
      : String(err).slice(0, _MAX_MESSAGE_LEN);
  const body = JSON.stringify({ kind: "observability_init_failed", message });
  try {
    // sendBeacon ignores all responses (the browser cannot read them
    // even if a CORS handshake succeeded). Passing a plain string sets
    // Content-Type to `text/plain;charset=UTF-8` automatically, which
    // is in the simple-CORS set so cross-origin sendBeacon skips
    // preflight (preflight + fire-and-forget don't compose).
    navigator.sendBeacon(_CLIENT_ERROR_BEACON_URL, body);
  } catch {
    // Never let the failure-reporter itself crash the app.
  }
}

function readEnvFlag(key: "VITE_OTEL_ENABLED"): boolean {
  const env = safeImportMetaEnv();
  return env[key] === "true";
}

function readEnvString(
  key: "VITE_OTEL_ENDPOINT" | "VITE_API_BASE_URL",
): string | undefined {
  const env = safeImportMetaEnv();
  const value = env[key];
  return typeof value === "string" && value.length > 0 ? value : undefined;
}

// OTel's fetch instrumentation only injects `traceparent` into outgoing
// requests whose URL matches an entry in this list. The app's API base lives
// under VITE_API_BASE_URL — if it's absolute and cross-origin, derive the
// matcher from it so frontend → backend spans correlate without callers
// having to pass it explicitly. Same-origin (relative base) needs nothing.
function derivePropagateUrlsFromEnv(): (string | RegExp)[] | undefined {
  const apiBase = readEnvString("VITE_API_BASE_URL");
  if (!apiBase) return undefined;
  // Same-origin (relative path like "/api/v1") needs no propagation matcher
  // — the OTel fetch instrumentor injects traceparent on same-origin
  // requests without one. Short-circuit before `new URL()` so the
  // legitimate relative-base case doesn't trigger the malformed-URL warn
  // below. A protocol-relative URL ("//host/path") is also treated as
  // same-origin per the browser, so skip it too.
  if (apiBase.startsWith("/")) return undefined;
  try {
    const origin = new URL(apiBase).origin;
    return [origin];
  } catch (err) {
    // A typo in VITE_API_BASE_URL would silently disable trace-header
    // propagation across the FE → BE boundary — spans on each side would
    // exist but never correlate. Surface the failure to the console so a
    // dev rebuilding with a bad value sees it; production bundles
    // already report init-level failures via the backend beacon, but
    // this helper runs even on partial success of initObservability.
    console.warn(
      "[observability] derivePropagateUrlsFromEnv: malformed VITE_API_BASE_URL; trace-header propagation disabled",
      err,
    );
    return undefined;
  }
}

function safeImportMetaEnv(): Record<string, string | undefined> {
  try {
    return import.meta.env;
  } catch (err) {
    // import.meta.env is a Vite-injected static object — under normal
    // builds this never throws. A throw here means the bundle is being
    // executed in a non-Vite context (e.g. a Node script importing the
    // module directly, or a future bundler regression that drops the
    // static replacement). Default to an empty env so the observability
    // flag stays false instead of crashing the app, but warn so the
    // dev sees the unusual context.
    console.warn(
      "[observability] import.meta.env unavailable; OTEL flags disabled",
      err,
    );
    return {};
  }
}
