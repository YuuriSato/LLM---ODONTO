# Telemetria de teste da API MedGemma

O gateway expõe `GET /v1/telemetry` usando a mesma chave Bearer da API do modelo. O endpoint retorna um resumo e os 200 eventos mais recentes de `POST /v1/chat/completions` desde que o processo iniciou. Cada evento contém horário UTC, status HTTP, duração, modelo e, quando fornecida pelo LM Studio, contagem de tokens. Inclui também tentativas recusadas. Os dados ficam somente na memória e desaparecem ao reiniciar o gateway.

O endpoint não retorna prompts, respostas, imagens, chave, endereço IP nem cabeçalhos. Chamadas a `/v1/models` e `/v1/telemetry` não entram na contagem. Uma ferramenta de observabilidade precisa fazer `GET` nessa rota com `Authorization: Bearer <chave>` pelo seu backend; inserir a chave no navegador a expõe aos visitantes. O formato é específico deste projeto e pode não ser reconhecido automaticamente por painéis que aceitam apenas a API padrão de chat.

Exemplo no PowerShell, na raiz do projeto, sem mostrar a chave:

```powershell
$apiKey = (Get-Content -LiteralPath 'runtime/private_bundles/medgemma_public_api.key' -Raw).Trim()
Invoke-RestMethod `
  -Uri 'https://opens-automobile-delhi-painted.trycloudflare.com/v1/telemetry' `
  -Headers @{ Authorization = "Bearer $apiKey" }
```

O Quick Tunnel usa uma URL temporária. Após mudar a URL, atualize o endereço na ferramenta. É necessário reiniciar o processo `scripts.public_model_gateway` para ativar este endpoint; os eventos anteriores ao reinício não estarão disponíveis.
