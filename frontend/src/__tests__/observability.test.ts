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
    expect(config?.["@opentelemetry/instrumentation-fetch"]).toEqual(
      expect.objectContaining({
        propagateTraceHeaderCorsUrls: ["http://localhost:8000"],
      }),
    );
  });

  it("does not derive propagation URLs when VITE_API_BASE_URL is relative", async () => {
    vi.stubEnv("VITE_OTEL_ENABLED", "true");
    vi.stubEnv("VITE_API_BASE_URL", "/api/v1");
    const { initObservability } = await importFreshModule();
    await initObservability();
    const config = lastInstrumentationConfig();
    expect(
      config?.["@opentelemetry/instrumentation-fetch"]?.propagateTraceHeaderCorsUrls,
    ).toBeUndefined();
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
    const sendBeacon = vi.fn(() => true);
    vi.stubGlobal("navigator", { sendBeacon });
    providerRegister.mockImplementationOnce(() => {
      throw new Error("VITE_OTEL_ENDPOINT typo'd");
    });
    const { initObservability } = await importFreshModule();

    const result = await initObservability({ enabled: true });
    expect(result).toBe(false);
    expect(sendBeacon).toHaveBeenCalledTimes(1);
    const [url, body] = sendBeacon.mock.calls[0] as [string, string];
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
