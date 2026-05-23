import { getWebAutoInstrumentations } from "@opentelemetry/auto-instrumentations-web";
import { OTLPTraceExporter } from "@opentelemetry/exporter-trace-otlp-http";
import { registerInstrumentations } from "@opentelemetry/instrumentation";
import { resourceFromAttributes } from "@opentelemetry/resources";
import { BatchSpanProcessor, WebTracerProvider } from "@opentelemetry/sdk-trace-web";
import { ATTR_SERVICE_NAME } from "@opentelemetry/semantic-conventions";

const DEFAULT_ENDPOINT = "http://localhost:4318/v1/traces";
const DEFAULT_SERVICE_NAME = "ams-frontend";

export interface InitObservabilityOptions {
  enabled?: boolean;
  endpoint?: string;
  serviceName?: string;
  propagateTraceHeaderCorsUrls?: (string | RegExp)[];
}

let initialized = false;

export function initObservability(options: InitObservabilityOptions = {}): boolean {
  const enabled = options.enabled ?? readEnvFlag("VITE_OTEL_ENABLED");
  if (!enabled) return false;
  if (initialized) return false;

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
  try {
    const origin = new URL(apiBase).origin;
    return [origin];
  } catch {
    return undefined;
  }
}

function safeImportMetaEnv(): Record<string, string | undefined> {
  try {
    return import.meta.env;
  } catch {
    return {};
  }
}
