# Worker de observabilidade e API do modelo

O Worker existente `observability-okta7` continua enviando as rotas do painel para `UPSTREAM_ORIGIN`. Apenas estas rotas usam `MODEL_ORIGIN`:

- `GET /v1/models`
- `GET /v1/telemetry`
- `POST /v1/chat/completions`

A Base URL pública do modelo é `https://observability-okta7.okta7.workers.dev/v1`. O Worker apenas encaminha requisições; a chave Bearer continua sendo validada pelo gateway local. Não há chave no código ou nas variáveis do Worker. O endereço do Worker é fixo, mas `MODEL_ORIGIN` ainda aponta para um Quick Tunnel temporário.

## Atualizar o túnel de origem

Antes de publicar, obtenha o endereço atual do Quick Tunnel do modelo e o valor já existente de `UPSTREAM_ORIGIN` no Worker. Configure no PowerShell, sem colocar os valores no Git:

```powershell
$env:OBSERVABILITY_ORIGIN = '<origem atual do painel>'
$env:MEDGEMMA_ORIGIN = '<origem atual do túnel do modelo>'
cd cloudflare/observability_proxy
npm ci
cf workers versions create --dry-run
cf deploy
```

Depois, teste `/login` e `/v1/models` no endereço público. A rota `/v1/telemetry` requer a versão atualizada do gateway local. Se o Quick Tunnel mudar, atualize `MEDGEMMA_ORIGIN` e publique novamente. Use um `User-Agent` que identifique o cliente ao chamar a URL `workers.dev`; o `User-Agent` padrão de `urllib` pode receber HTTP 403 da Cloudflare.
