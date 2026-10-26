import { bindings, defineConfig } from "cf/config";
import * as entrypoint from "./index.mjs" with { type: "cf-worker" };

const observabilityOrigin = process.env.OBSERVABILITY_ORIGIN;
const modelOrigin = process.env.MEDGEMMA_ORIGIN;
if (!observabilityOrigin || !modelOrigin) {
  throw new Error("Set OBSERVABILITY_ORIGIN and MEDGEMMA_ORIGIN before building or deploying.");
}

export default defineConfig({
  accountId: "34f73f37da1825c5543dead0c138f09b",
  worker: {
    name: "observability-okta7",
    compatibilityDate: "2026-10-26",
    entrypoint,
    workersDev: true,
    previewUrls: true,
    env: {
      UPSTREAM_ORIGIN: bindings.text(observabilityOrigin),
      MODEL_ORIGIN: bindings.text(modelOrigin),
    },
    observability: {
      enabled: true,
      headSamplingRate: 0.1,
      logs: { enabled: true, headSamplingRate: 0.1, invocationLogs: true, persist: true },
      traces: { enabled: true, headSamplingRate: 0.1, persist: true },
    },
  },
});
