# Chat de teste do MedGemma Dental LoRA

Esta página testa a API remota pelo Quick Tunnel. O navegador não recebe a chave: o pequeno servidor Python a lê de um arquivo local ignorado pelo Git e envia as requisições HTTPS com `stream=false`.

Mantenha o LM Studio, o gateway na porta 8765 e o Quick Tunnel ligados. No PowerShell, na raiz do projeto, substitua a URL se o túnel tiver reiniciado:

```powershell
.\.venv\Scripts\python.exe -m scripts.chat_test_web `
  --base-url 'https://opens-automobile-delhi-painted.trycloudflare.com/v1' `
  --key-file 'runtime/private_bundles/medgemma_public_api.key' `
  --port 8766
```

Abra `http://127.0.0.1:8766/`. O servidor escuta apenas no loopback desta máquina. O chat é somente texto, mantém o histórico na memória da página e não grava as mensagens. Se a URL temporária mudar, reinicie o servidor com a nova Base URL.

O modelo ainda é experimental: a interface demonstra conectividade, não precisão ou segurança clínica.
