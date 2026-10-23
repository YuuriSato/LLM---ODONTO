# Ambiente local

Repositório baixado diretamente nesta pasta, branch `main`.

Visual Studio Code e Node.js instalados. Dependências Python em `.venv`; dependências React em `node_modules`.

## Abrir para editar

Abra esta pasta no Visual Studio Code. Interface: `frontend/src/`. Backend: `app/`.

## Iniciar a interface compilada

No PowerShell, dentro desta pasta:

```powershell
.\iniciar-local.ps1
```

Abra http://127.0.0.1:9090. Para parar, use Ctrl+C no terminal do servidor.

## Editar com atualização automática

Mantenha o backend acima ligado e, em outro terminal, execute:

```powershell
npm run dev
```

Abra http://127.0.0.1:5173. Se o terminal já estava aberto antes da instalação do Node.js, reabra o VS Code para atualizar o PATH.

Depois das alterações, `npm run build` atualiza a versão servida na porta 9090.

O `.env` local usa `APP_ENV=development`. Para análise com Gemini, preencha `GEMINI_API_KEY` no `.env`. A interface pode abrir sem a chave; a análise remota depende dela. Para modelos locais, configure o LM Studio conforme o README original.

O backend pode estar em segundo plano. Para encerrá-lo, aguarde as análises terminarem e execute `./parar-local.ps1`. O script confere se o processo da porta 9090 pertence a este projeto antes de encerrá-lo. Depois inicie pelo script acima. Logs ficam em `logs/local-backend.*.log`.

O Vite foi atualizado para 8.3.5, com lockfile atualizado; a auditoria npm não apontou vulnerabilidades após essa atualização. Build e testes de interface foram executados.

## Fine-tuning

Consulte `fine_tuning/HISTORICO.md`, `fine_tuning/README.md` e `fine_tuning/REDE_NEURAL.md`. Há uma CNN experimental com treino de engenharia verificado. O treino odontológico depende da revisão do dataset.

## Conhecimento no Obsidian

Abra a pasta `obsidian` como um cofre e comece em `Inicio.md`. Para atualizar o resumo agregado, execute `.\.venv\Scripts\python.exe scripts/export_obsidian.py`.
