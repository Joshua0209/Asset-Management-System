import { beforeEach, describe, expect, it, vi } from "vitest";

interface WebProviderArgs {
  resource: unknown;
  spanProcessors: unknown[];
}

interface InstrumentationConfig {
  "@opentelemetry/instrumentation-xml-http-request"?: { enabled?: boolean };
  "@opentelemetry/instrumentation-fetch"?: {
    propagateTraceHeaderCorsUrls?: (string | RegExp)[];
  };
}

const providerRegister = vi.fn();
const WebTracerProviderMock = vi.fn(() => ({ register: providerRegister }));
const BatchSpanProcessorMock = vi.fn(function BSP(this: object, exporter: unknown) {
  Object.assign(this, { exporter });
});
const OTLPTraceExporterMock = vi.fn(function Exporter(this: object, cfg: unknown) {
  Object.assign(this, { cfg });
});
const resourceFromAttributesMock = vi.fn((attrs: Record<string, unknown>) => ({ attrs }));
const registerInstrumentationsMock = vi.fn();
const getWebAutoInstrumentationsMock = vi.fn((): string[] => ["fake-instrumentation"]);

function lastProviderArgs(): WebProviderArgs | undefined {
  const calls = WebTracerProviderMock.mock.calls as unknown as WebProviderArgs[][];
  const last = calls[calls.length - 1];
  return last ? last[0] : undefined;
}

function lastInstrumentationConfig(): InstrumentationConfig | undefined {
  const calls = getWebAutoInstrumentationsMock.mock.calls as unknown as Array<
    [InstrumentationConfig | undefined]
  >;
  const last = calls[calls.length - 1];
  return last ? last[0] : undefined;
}

vi.mock("@opentelemetry/sdk-trace-web", () => ({
  WebTracerProvider: WebTracerProviderMock,
  BatchSpanProcessor: BatchSpanProcessorMock,
}));

vi.mock("@opentelemetry/exporter-trace-otlp-http", () => ({
  OTLPTraceExporter: OTLPTraceExporterMock,
}));

vi.mock("@opentelemetry/resources", () => ({
  resourceFromAttributes: resourceFromAttributesMock,
}));

vi.mock("@opentelemetry/instrumentation", () => ({
  registerInstrumentations: registerInstrumentationsMock,
}));

vi.mock("@opentelemetry/auto-instrumentations-web", () => ({
  getWebAutoInstrumentations: getWebAutoInstrumentationsMock,
}));

async function importFreshModule() {
  vi.resetModules();
  return await import("../observability");
}

describe("initObservability", () => {
  beforeEach(() => {
    WebTracerProviderMock.mockClear();
    BatchSpanProcessorMock.mockClear();
    OTLPTraceExporterMock.mockClear();
    resourceFromAttributesMock.mockClear();
    registerInstrumentationsMock.mockClear();
    getWebAutoInstrumentationsMock.mockClear();
    providerRegister.mockClear();
    providerRegister.mockReset();
    vi.unstubAllEnvs();
  });

  it("does nothing when explicitly disabled", async () => {
    const { initObservability } = await importFreshModule();
    const result = await initObservability({ enabled: false });
    expect(result).toBe(false);
    expect(WebTracerProviderMock).not.toHaveBeenCalled();
    expect(registerInstrumentationsMock).not.toHaveBeenCalled();
  });

  it("uses the default endpoint and service name when none provided", async () => {
    const { initObservability } = await importFreshModule();
    const result = await initObservability({ enabled: true });
    expect(result).toBe(true);
    expect(OTLPTraceExporterMock).toHaveBeenCalledWith(
      expect.objectContaining({ url: "http://localhost:4318/v1/traces" }),
    );
    expect(resourceFromAttributesMock).toHaveBeenCalledWith(
      expect.objectContaining({ "service.name": "ams-frontend" }),
    );
  });

  it("passes a custom endpoint to the OTLP exporter", async () => {
    const { initObservability } = await importFreshModule();
    await initObservability({
      enabled: true,
      endpoint: "https://otel.example.com/v1/traces",
    });
    expect(OTLPTraceExporterMock).toHaveBeenCalledWith(
      expect.objectContaining({ url: "https://otel.example.com/v1/traces" }),
    );
  });

  it("registers the tracer provider exactly once across repeated calls", async () => {
    const { initObservability } = await importFreshModule();
    const first = await initObservability({ enabled: true });
    const second = await initObservability({ enabled: true });
    expect(first).toBe(true);
    expect(second).toBe(false);
    expect(WebTracerProviderMock).toHaveBeenCalledTimes(1);
    expect(providerRegister).toHaveBeenCalledTimes(1);
    expect(registerInstrumentationsMock).toHaveBeenCalledTimes(1);
  });

  it("enables fetch + document-load auto instrumentations and disables XHR", async () => {
    const { initObservability } = await importFreshModule();
    await initObservability({
      enabled: true,
      propagateTraceHeaderCorsUrls: [/^http:\/\/localhost:8000/],
    });
    expect(getWebAutoInstrumentationsMock).toHaveBeenCalledTimes(1);
    const config = lastInstrumentationConfig();
    expect(config).toBeDefined();
    expect(config?.["@opentelemetry/instrumentation-xml-http-request"]).toEqual({
      enabled: false,
    });
    expect(config?.["@opentelemetry/instrumentation-fetch"]).toEqual(
      expect.objectContaining({
        propagateTraceHeaderCorsUrls: [/^http:\/\/localhost:8000/],
      }),
    );
    expect(registerInstrumentationsMock).toHaveBeenCalledWith(
      expect.objectContaining({ instrumentations: ["fake-instrumentation"] }),
    );
  });

  it("reads VITE_OTEL_ENABLED and VITE_OTEL_ENDPOINT from env on zero-arg startup", async () => {
    vi.stubEnv("VITE_OTEL_ENABLED", "true");
    vi.stubEnv("VITE_OTEL_ENDPOINT", "https://otel.example.com/v1/traces");
    const { initObservability } = await importFreshModule();
    const result = await initObservability();
    expect(result).toBe(true);
    expect(OTLPTraceExporterMock).toHaveBeenCalledWith(
      expect.objectContaining({ url: "https://otel.example.com/v1/traces" }),
    );
  });

  it("derives propagateTraceHeaderCorsUrls from VITE_API_BASE_URL when cross-origin", async () => {
    vi.stubEnv("VITE_OTEL_ENABLED", "true");
    vi.stubEnv("VITE_API_BASE_URL", "http://localhost:8000/api/v1");
    const { initObservability } = await importFreshModule();
    await initObservability();
    const config = lastInstrumentationConfig();
    const urls =
      config?.["@opentelemetry/instrumentation-fetch"]?.propagateTraceHeaderCorsUrls;
    // The matcher is a path-anchored regex (not a bare prefix string)
    // so a lookalike origin like ``http://localhost:8000.evil.com``
    // cannot match. Pin both the structural shape (length 1, RegExp)
    // and the matching behavior on representative URLs.
    expect(Array.isArray(urls)).toBe(true);
    expect(urls).toHaveLength(1);
    const matcher = urls?.[0];
    expect(matcher).toBeInstanceOf(RegExp);
    const re = matcher as RegExp;
    expect(re.test("http://localhost:8000")).toBe(true);
    expect(re.test("http://localhost:8000/api/v1/assets")).toBe(true);
    // Path-boundary anchor rejects lookalike hosts.
    expect(re.test("http://localhost:8000.evil.com/x")).toBe(false);
    expect(re.test("http://localhost:8000evil/x")).toBe(false);
  });

  it("does not derive propagation URLs when VITE_API_BASE_URL is relative", async () => {
    // Relative URLs (`/api/v1`) are same-origin by definition — OTel's
    // fetch instrumentor injects `traceparent` on same-origin requests
    // without a propagation matcher. The short-circuit prevents `new
    // URL("/api/v1")` from throwing and triggering the malformed-URL
    // warning below — pin that no console.warn fires on this path.
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    vi.stubEnv("VITE_OTEL_ENABLED", "true");
    vi.stubEnv("VITE_API_BASE_URL", "/api/v1");
    const { initObservability } = await importFreshModule();
    await initObservability();
    const config = lastInstrumentationConfig();
    expect(
      config?.["@opentelemetry/instrumentation-fetch"]?.propagateTraceHeaderCorsUrls,
    ).toBeUndefined();
    expect(warn).not.toHaveBeenCalledWith(
      expect.stringContaining("malformed VITE_API_BASE_URL"),
      expect.anything(),
    );
    warn.mockRestore();
  });

  it("warns and disables propagation when VITE_API_BASE_URL is malformed", async () => {
    // A typo'd absolute URL (e.g. missing protocol) would silently
    // disable cross-origin trace correlation between FE and BE — spans
    // exist on each side but never join. The H4 fix logs to console.warn
    // so a dev rebuilding with a bad value sees the failure instead of
    // wondering why their Tempo traces are orphaned. Returns undefined
    // so initObservability proceeds without a matcher.
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    vi.stubEnv("VITE_OTEL_ENABLED", "true");
    vi.stubEnv("VITE_API_BASE_URL", "not a real url at all");
    const { initObservability } = await importFreshModule();
    await initObservability();
    const config = lastInstrumentationConfig();
    expect(
      config?.["@opentelemetry/instrumentation-fetch"]?.propagateTraceHeaderCorsUrls,
    ).toBeUndefined();
    expect(warn).toHaveBeenCalledWith(
      expect.stringContaining("malformed VITE_API_BASE_URL"),
      expect.any(Error),
    );
    warn.mockRestore();
  });

  it("prefers an explicit propagateTraceHeaderCorsUrls option over the env-derived default", async () => {
    vi.stubEnv("VITE_OTEL_ENABLED", "true");
    vi.stubEnv("VITE_API_BASE_URL", "http://localhost:8000/api/v1");
    const { initObservability } = await importFreshModule();
    await initObservability({ propagateTraceHeaderCorsUrls: [/^https:\/\/api\.prod\//] });
    const config = lastInstrumentationConfig();
    expect(config?.["@opentelemetry/instrumentation-fetch"]).toEqual(
      expect.objectContaining({
        propagateTraceHeaderCorsUrls: [/^https:\/\/api\.prod\//],
      }),
    );
  });

  it("constructs the tracer provider with the resource and a batch processor wrapping the exporter", async () => {
    const { initObservability } = await importFreshModule();
    await initObservability({ enabled: true });
    expect(WebTracerProviderMock).toHaveBeenCalledTimes(1);
    const providerArgs = lastProviderArgs();
    expect(providerArgs).toBeDefined();
    if (providerArgs === undefined) return;
    expect(providerArgs.resource).toEqual(
      expect.objectContaining({
        attrs: expect.objectContaining({ "service.name": "ams-frontend" }),
      }),
    );
    expect(providerArgs.spanProcessors).toHaveLength(1);
    expect(BatchSpanProcessorMock).toHaveBeenCalledWith(
      expect.objectContaining({ cfg: { url: "http://localhost:4318/v1/traces" } }),
    );
  });

  it("catches a provider.register() failure, logs, and leaves initialized=false so retries can proceed", async () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    providerRegister.mockImplementationOnce(() => {
      throw new Error("HMR re-register conflict");
    });
    const { initObservability } = await importFreshModule();

    const first = await initObservability({ enabled: true });
    expect(first).toBe(false);
    expect(warn).toHaveBeenCalledWith(
      "[observability] init failed; tracing disabled",
      expect.any(Error),
    );

    // initialized stayed false, so a clean retry runs end-to-end.
    const second = await initObservability({ enabled: true });
    expect(second).toBe(true);
    expect(providerRegister).toHaveBeenCalledTimes(2);

    warn.mockRestore();
  });

  it("posts a navigator.sendBeacon to the backend when init fails so operators see the regression", async () => {
    // Without this beacon, a misconfigured prod bundle silently disables
    // tracing for 100% of users — indistinguishable from
    // VITE_OTEL_ENABLED=false from the operator's view. The beacon
    // increments the backend's ams_frontend_observability_init_failures_total
    // counter so an alert rule catches the regression in the next deploy.
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    const sendBeacon = vi.fn<(url: string, body: string) => boolean>(() => true);
    vi.stubGlobal("navigator", { sendBeacon });
    providerRegister.mockImplementationOnce(() => {
      throw new Error("VITE_OTEL_ENDPOINT typo'd");
    });
    const { initObservability } = await importFreshModule();

    const result = await initObservability({ enabled: true });
    expect(result).toBe(false);
    expect(sendBeacon).toHaveBeenCalledTimes(1);
    const [url, body] = sendBeacon.mock.calls[0];
    expect(url).toBe("/api/v1/observability/client-error");
    // Passing a string makes the browser set Content-Type to
    // `text/plain;charset=UTF-8` automatically — in the simple-CORS
    // set, so a future cross-origin deploy skips the preflight that
    // fire-and-forget sendBeacon cannot satisfy.
    expect(typeof body).toBe("string");
    const parsed = JSON.parse(body) as { kind: string; message: string };
    expect(parsed.kind).toBe("observability_init_failed");
    expect(parsed.message).toContain("VITE_OTEL_ENDPOINT");

    warn.mockRestore();
    vi.unstubAllGlobals();
  });

  it("does not throw when navigator.sendBeacon returns false (queue full / URL rejected)", async () => {
    // sendBeacon returns false when the browser refuses to enqueue the
    // request (queue full, URL rejected by browser policy, etc.). The
    // catch block in observability.ts must treat this as a no-op — a
    // regression that did ``if (!navigator.sendBeacon(...)) throw`` or
    // recursed on false would crash the page. Pin the contract.
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    const sendBeacon = vi.fn<(url: string, body: string) => boolean>(() => false);
    vi.stubGlobal("navigator", { sendBeacon });
    providerRegister.mockImplementationOnce(() => {
      throw new Error("init failure under beacon-queue-full");
    });
    const { initObservability } = await importFreshModule();

    const result = await initObservability({ enabled: true });
    expect(result).toBe(false);
    expect(sendBeacon).toHaveBeenCalledTimes(1);
    // The console.warn for the init failure still fires (so the dev
    // notices in DevTools). The beacon being dropped is silent on
    // purpose — operators cannot see beacon-queue-full anyway.
    expect(warn).toHaveBeenCalled();

    warn.mockRestore();
    vi.unstubAllGlobals();
  });

  it("does not throw when dynamic import of an OTel SDK chunk rejects", async () => {
    // The whole point of the dynamic-import block at the top of
    // initObservability is to keep the ~80-120 KB OTel browser SDK
    // out of the disabled-default bundle. If one of the six chunk
    // loads rejects at runtime (chunk 404'd after a partial CDN
    // deploy, the wrong-version peer dep, network blip), the catch
    // block must still:
    //   - log to console.warn for the dev
    //   - fire the backend beacon so operators see the regression
    //   - leave initialized=false so a retry can proceed
    // A regression that moved provider construction into static
    // imports (defeating the bundle-size goal) would mean this
    // failure mode could never trigger — and would silently re-add
    // ~100 KB to every production bundle.
    //
    // Mocking the dynamic ``import("@opentelemetry/sdk-trace-web")``
    // to reject is awkward in vitest 4 — ``vi.doMock`` factory throws
    // get wrapped in a vitest meta-error before reaching our catch
    // block, so we can't assert the original message verbatim. We CAN
    // assert the structural contract: init returns false, the beacon
    // fires, and the catch block logged a warn. That's what proves
    // the dynamic-import-failure path is wired correctly.
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    const sendBeacon = vi.fn<(url: string, body: string) => boolean>(() => true);
    vi.stubGlobal("navigator", { sendBeacon });
    vi.resetModules();
    vi.doMock("@opentelemetry/sdk-trace-web", () => {
      throw new Error("chunk load failed: /assets/otel-sdk-trace-web.<hash>.js");
    });
    const { initObservability } = await import("../observability");

    const result = await initObservability({ enabled: true });
    expect(result).toBe(false);
    expect(warn).toHaveBeenCalledWith(
      "[observability] init failed; tracing disabled",
      expect.any(Error),
    );
    expect(sendBeacon).toHaveBeenCalledTimes(1);
    const [url, body] = sendBeacon.mock.calls[0];
    expect(url).toBe("/api/v1/observability/client-error");
    const parsed = JSON.parse(body) as { kind: string; message: string };
    expect(parsed.kind).toBe("observability_init_failed");
    // The wrapped error contains the original "chunk load failed" cause
    // when vitest serializes Error.message via String(err). Either the
    // raw factory throw or the vitest meta-error wrapper indicates the
    // catch block fired — both satisfy the contract.
    expect(parsed.message.length).toBeGreaterThan(0);

    // Restore the original mock factory before the next test runs.
    // vi.doUnmock alone is insufficient — vi.resetModules() in
    // importFreshModule() re-evaluates the doMock factory unless we
    // overwrite it with the original suite-wide shape.
    vi.doMock("@opentelemetry/sdk-trace-web", () => ({
      WebTracerProvider: WebTracerProviderMock,
      BatchSpanProcessor: BatchSpanProcessorMock,
    }));
    warn.mockRestore();
    vi.unstubAllGlobals();
  });

  it("does not throw when navigator.sendBeacon synchronously throws (CSP / extension shim)", async () => {
    // The browser is allowed to make ``sendBeacon`` throw rather than
    // return false in several real-world scenarios:
    //   * CSP ``connect-src`` rejects the URL — Chromium throws
    //     ``TypeError: Failed to execute 'sendBeacon'``.
    //   * Brave / uBlock Origin / NoScript shim sendBeacon and may
    //     throw to surface a block decision to the page.
    //   * An oversized body can throw ``RangeError`` on some browsers.
    //
    // The M5 fix replaces the previous empty ``catch {}`` with
    // ``catch (beaconErr) { console.warn(...) }`` — locked here so a
    // future regression that re-empties the catch (or, worse, lets
    // the throw propagate) would fail this test. The app stays
    // running; the dev sees a clear DevTools warning.
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    const sendBeacon = vi.fn<(url: string, body: string) => boolean>(() => {
      throw new TypeError("Refused to connect (CSP)");
    });
    vi.stubGlobal("navigator", { sendBeacon });
    providerRegister.mockImplementationOnce(() => {
      throw new Error("init failure under CSP-blocked beacon");
    });
    const { initObservability } = await importFreshModule();

    // initObservability MUST resolve — the page does not crash.
    const result = await initObservability({ enabled: true });
    expect(result).toBe(false);
    // sendBeacon was attempted exactly once (no retry — fire-and-forget).
    expect(sendBeacon).toHaveBeenCalledTimes(1);
    // The dev sees two warnings: the init-failure warn AND the
    // M5 sendBeacon-threw warn. Both must fire for full diagnostic
    // surface.
    const warnings = warn.mock.calls.map((c) => String(c[0]));
    expect(
      warnings.some((m) => m.includes("sendBeacon threw")),
    ).toBe(true);

    warn.mockRestore();
    vi.unstubAllGlobals();
  });

  it("does not throw when navigator.sendBeacon is absent (older runtimes)", async () => {
    // The catch block in the catch block must never crash the app. A
    // jsdom runtime without sendBeacon (or a browser variant that
    // returns false / throws) must fall through to console-only
    // diagnostics without propagating.
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    vi.stubGlobal("navigator", {});
    providerRegister.mockImplementationOnce(() => {
      throw new Error("dynamic-import chunk failed");
    });
    const { initObservability } = await importFreshModule();

    const result = await initObservability({ enabled: true });
    expect(result).toBe(false);
    expect(warn).toHaveBeenCalled();

    warn.mockRestore();
    vi.unstubAllGlobals();
  });
});
