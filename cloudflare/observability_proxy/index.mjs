// Routes the model API through the existing observability Worker without
// changing the dashboard's other paths. Never logs requests or bodies.
const MODEL_ROUTES = new Map([
  ["/v1/models", "GET"],
  ["/v1/telemetry", "GET"],
  ["/v1/chat/completions", "POST"],
]);

function tunnelOrigin(value) {
  try {
    const url = new URL(value);
    if (url.protocol !== "https:" || !url.hostname.endsWith(".trycloudflare.com") ||
        url.username || url.password || url.pathname !== "/" || url.search || url.hash) return null;
    return url.origin;
  } catch {
    return null;
  }
}

async function proxy(request, incoming, origin, modelRoute) {
  const destination = new URL(incoming.pathname + incoming.search, origin);
  const websocket = request.headers.get("Upgrade")?.toLowerCase() === "websocket";
  const write = !["GET", "HEAD", "OPTIONS"].includes(request.method);
  if (!modelRoute && (write || websocket) && request.headers.get("Origin") !== incoming.origin) {
    return new Response("Origem não autorizada.", { status: 403 });
  }
  const headers = new Headers(request.headers);
  for (const key of ["host", "forwarded", "x-forwarded-host", "x-forwarded-proto"]) {
    headers.delete(key);
  }
  if (!modelRoute && (write || websocket)) headers.set("Origin", origin);
  if (modelRoute) headers.delete("Origin");
  try {
    const forwarded = new Request(destination, request);
    const response = await fetch(new Request(forwarded, { headers, redirect: "manual" }), {
      cf: { cacheTtl: 0, cacheEverything: false },
    });
    if (response.status === 101) return response;
    const result = new Response(response.body, response);
    result.headers.set("Cache-Control", "no-store");
    result.headers.set("X-Content-Type-Options", "nosniff");
    result.headers.set("X-Frame-Options", "DENY");
    result.headers.set("Referrer-Policy", "no-referrer");
    result.headers.set("X-Application", modelRoute ? "MedGemma Dental API" : "Observability OKTA7");
    if (!modelRoute) {
      const location = result.headers.get("Location");
      if (location) {
        const redirect = new URL(location, origin);
        if (redirect.origin === origin) {
          result.headers.set("Location", incoming.origin + redirect.pathname + redirect.search);
        }
      }
    }
    return result;
  } catch {
    console.error(JSON.stringify({ event: "origin_unavailable", application: modelRoute ? "medgemma-dental-api" : "observability-okta7" }));
    return new Response(modelRoute ? "API do modelo indisponível." : "OKTA7 LLM: o computador de monitoramento está desconectado. Verifique o túnel local.", {
      status: 503,
      headers: { "Content-Type": "text/plain; charset=utf-8", "Cache-Control": "no-store" },
    });
  }
}

export default {
  async fetch(request, env) {
    const incoming = new URL(request.url);
    const modelMethod = MODEL_ROUTES.get(incoming.pathname);
    const modelRoute = modelMethod !== undefined;
    if (modelRoute && request.method !== modelMethod) {
      return new Response("Método não permitido.", { status: 405, headers: { Allow: modelMethod } });
    }
    const origin = tunnelOrigin(modelRoute ? env.MODEL_ORIGIN : env.UPSTREAM_ORIGIN);
    if (!origin) {
      return new Response(modelRoute ? "Destino da API do modelo não configurado." : "Destino de observabilidade não configurado.", { status: 503 });
    }
    return proxy(request, incoming, origin, modelRoute);
  },
};
