---
tags: [lm-odonto, mapa]
---

# LM Odonto

Objetivo: analisar integridade de imagens odontológicas com evidências rastreáveis, respostas coerentes e avaliação independente. O sistema não fornece diagnóstico clínico.

Abra esta pasta como um cofre no Obsidian: **Open folder as vault**. O grafo de notas aparece a partir dos links abaixo. Não requer plugins comunitários.

Linha de trabalho: [[Arquitetura]] → [[Qualidade e contradicoes]] → [[Validacao]] → [[Dataset]] → [[Rede neural]] → [[Decisoes]]. Consulte também [[Fontes]] e [[Gerado/Estado do projeto]].

O código continua na pasta pai. A documentação técnica detalhada está em `../docs/ESTUDO_INTEGRIDADE_E_INCONCLUSIVAS.md`.

Evidências e pendências atuais: [[Verificacao local]].

Verificação do repositório em 23/10/2026: `../docs/VERIFICACAO_GITHUB_DATASET.md` distingue a base documentada de 103 imagens dos resultados efetivamente publicados.

Para atualizar as contagens do projeto, execute na raiz:

```powershell
.\.venv\Scripts\python.exe scripts/export_obsidian.py
```

As notas escritas manualmente permanecem sob seu controle. O exportador atualiza apenas arquivos que ele criou e que não foram editados desde a última exportação. Conflitos são informados, sem sobrescrever sua edição.
