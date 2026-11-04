# Codex — LM Odonto / Sato Company

Guia de trabalho baseado no cofre [`obsidian/`](obsidian/Inicio.md). Leia as notas originais quando precisar da evidência completa. As entradas têm datas diferentes; para o estado atual, consulte também [`Acompanhamento treinamento`](obsidian/Acompanhamento%20treinamento.md), [`docs/MODEL_CARD_MEDGEMMA_DENTAL_LORA.md`](docs/MODEL_CARD_MEDGEMMA_DENTAL_LORA.md) e o código. Não interprete uma pendência registrada em 22 ou 23/10/2026 como estado atual sem verificá-la.

## Objetivo e limites

- Analisar a integridade de imagens odontológicas com evidências rastreáveis, respostas coerentes e avaliação independente. O sistema não fornece diagnóstico clínico.
- Dimensões, qualidade global, visibilidade de uma região e autenticidade são questões distintas. Uma imagem de qualidade geral boa ainda pode ter uma região ilegível.
- Ausência de anomalias, EXIF ou metadados não comprova autenticidade nem fraude. Não converta uma resposta inconclusiva em `REAL` para aumentar a cobertura.
- Separe análise concluída, inconclusiva, impossível de avaliar, falha técnica e resposta contraditória. Guarde as medições e respostas que fundamentaram cada estado.
- Uma lista de modelos disponíveis ou uma chamada bem-sucedida comprova integração técnica, não acerto da análise. Não apresente saída ou softmax como probabilidade calibrada de autenticidade.

## Mapa do projeto

| Área | Local | Função |
| --- | --- | --- |
| Interface | `frontend/src/` | Seleção do modelo, envio e resultado |
| Serviço e análise | `app/`, `app/ai/` | Upload, medições, provedor visual, auditoria e histórico |
| CNN experimental | `app/neural/`, `scripts/training/train_neural.py` | Treino e predição separados do modelo principal |
| Fine-tuning MedGemma | `scripts/training/`, `fine_tuning/` | Preparação, treino, fusão e exportação |
| Cofre Obsidian | `obsidian/` | Decisões, pesquisa, evidências e limitações |
| Testes | `tests/` | Contratos de software e fluxos da interface |

O fluxo principal é: upload → validação e hash → medições locais → modelo visual selecionado → schema e referências → auditoria de coerência → revisão de conflito → resultado e histórico. A escolha do provedor deve ser explícita; não troque silenciosamente LM Studio por Gemini ou vice-versa.

## Dados e treinamento

- O JSONL legado tem 1.902 registros (`REAL` 1.352, alterações manuais 250, digitais 250 e indeterminado 50), sem classe de IA. Nomes de pastas são candidatos a rótulo, não confirmação de procedência.
- O inventário anotado no Obsidian registra 3.254 arquivos, 1.386 hashes únicos e 1.868 duplicatas. A reprodução de 550 variantes comprova a relação técnica com uma imagem-base, não a origem clínica da base.
- A fonte Mendeley OPG versão 4 é candidata para parte do acervo. A identidade dos arquivos locais com os publicados ainda requer comparação de hashes; imagens aumentadas não devem receber automaticamente o rótulo `REAL`.
- Cada amostra usada para avaliar ou treinar um detector precisa de hash, procedência, rótulo verificado, grupo por paciente/original e partição. Variantes do mesmo original ficam na mesma partição. Reserve o teste antes de escolher modelo ou limiar.
- As quatro classes previstas para um manifesto revisado são `REAL`, `EDICAO_TRADICIONAL`, `IA_GERADA` e `IA_EDITADA`. Previsões de LLM não servem como verdade de referência.
- O treino LoRA MedGemma 1.5 registrado terminou em 476 passos e gerou adaptador, GGUF Q4_K_M e projetor visual local. O LM Studio carregou o modelo multimodal. Esse treino usou dados legados, sem classe IA e sem teste independente registrado; perda de treino e carregamento não medem generalização. Um controle sem imagem gerou a mesma resposta que o teste com imagem. Trate o modelo como experimental.
- A CNN treinada com padrões geométricos verifica somente a infraestrutura. Não a apresente como detector odontológico validado.

## Operação local

Para iniciar a interface compilada, execute `./iniciar-local.ps1` e abra `http://127.0.0.1:9090/`. Para desenvolvimento do frontend, use `npm run dev`; após mudanças na interface, `npm run build` atualiza o conteúdo servido na porta 9090. Consulte [`LEIA-ME-LOCAL.md`](LEIA-ME-LOCAL.md) antes de alterar serviços ou portas.

O GGUF dental usa `AI_PROVIDER=lmstudio` e `LM_STUDIO_MODEL=medgemma-dental-lora-1.5` no `.env` local. Carregue o modelo com projetor visual e contexto de pelo menos 8192 tokens: o contexto de 4096 produziu HTTP 400 por exceder o limite na requisição do Sato Company. O teste sintético em `scripts/provider_check.py` confirma transporte, schema e auditoria, não precisão.

## Verificação de mudanças

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py"
npm run build
npm run test:ui
.\.venv\Scripts\python.exe scripts/check_private_files.py
```

Use `BROWSER_CHANNEL=chrome` para o smoke test de interface quando o Chromium do Playwright não estiver instalado. Meça separadamente modalidade, coerência, cobertura, erro nas decisões aceitas, falsos positivos de IA, falhas técnicas, abstenções, latência e repetibilidade em dados independentes. Testes de software não substituem essa avaliação.

## Privacidade e registro

- Não publique `.env`, chaves, imagens privadas importadas, históricos, checkpoints, adaptadores ou GGUF no repositório público. `fine_tuning/datasets/`, `runs/` e `exports/` contêm artefatos locais ignorados pelo Git.
- Preserve o upload original e os hashes; não sobrescreva checkpoints nem resultados anteriores. Documente mudanças de decisão com motivo, evidência, risco e critério de avaliação.
- O exportador `scripts/export_obsidian.py` atualiza somente suas próprias notas geradas e evita sobrescrever edições manuais. Mantenha fatos novos e limites de validação nas notas relevantes.

## Notas de referência

Comece por [`Inicio`](obsidian/Inicio.md), [`Arquitetura`](obsidian/Arquitetura.md), [`Qualidade e contradições`](obsidian/Qualidade%20e%20contradicoes.md), [`Dataset`](obsidian/Dataset.md), [`Rede neural`](obsidian/Rede%20neural.md), [`Validação`](obsidian/Validacao.md) e [`Decisões`](obsidian/Decisoes.md). Fontes externas e sua interpretação estão em [`Fontes`](obsidian/Fontes.md) e [`Origem OPG`](obsidian/Origem%20OPG.md).
