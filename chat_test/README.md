# Chat de teste do MedGemma Dental LoRA

Esta página testa a API remota pelo Quick Tunnel. O navegador não recebe a chave: o pequeno servidor Python a lê de um arquivo local ignorado pelo Git e envia as requisições HTTPS com `stream=false`.

Mantenha o LM Studio, o gateway na porta 8765 e o Quick Tunnel ligados. No PowerShell, na raiz do projeto:

```powershell
.\.venv\Scripts\python.exe -m scripts.chat_test_web `
  --base-url 'https://observability-okta7.okta7.workers.dev/v1' `
  --key-file 'runtime/private_bundles/medgemma_public_api.key' `
  --port 8766
```

Abra `http://127.0.0.1:8766/`. O servidor escuta apenas no loopback desta máquina. O chat aceita texto e uma imagem PNG, JPEG ou WebP de até 5 MB por conversa. A imagem é enviada à API como `image_url` em base64; WebP é convertido para PNG no servidor local. O histórico permanece na memória da página e não é gravado em disco. Use **Nova conversa** para trocar de imagem. O endereço externo é fixo, mas ainda depende do Quick Tunnel entre o Worker e esta máquina.

Após atualizar o código, interrompa o servidor anterior com `Ctrl+C`, execute o comando acima novamente e recarregue a página.

O modelo ainda é experimental: a interface demonstra conectividade, não precisão ou segurança clínica.
