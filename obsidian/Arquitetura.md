---
tags: [lm-odonto, arquitetura]
---

# Arquitetura

[[Inicio]] · [[Qualidade e contradicoes]] · [[Rede neural]] · [[Validacao]]

```mermaid
flowchart TD
    A[Upload original] --> B[Validação de arquivo e hash]
    B --> C[Medidas locais e limitações]
    B --> D[Modelo visual selecionado]
    C --> D
    D --> E[Schema e referências]
    E --> F[Auditoria e coerência]
    F -->|Conflito| G[Revisão explícita]
    G --> F2[Auditoria final]
    F -->|Sem conflito| H[Resultado e histórico]
    F2 -->|Resolvido| H
    F2 -->|Contradição persistente| I[Resposta não validada]
    I --> H
    H --> J[Resumo agregado no Obsidian]
```

React apresenta a análise; Python executa medições, chama Gemini ou LM Studio e persiste os resultados. O caminho de inferência local exige modo de desenvolvimento. A rede CNN é experimental e possui treino e predição próprios, descritos em [[Rede neural]].

Nenhuma escolha de provedor deve ocorrer silenciosamente. Listar um modelo não demonstra que ele compreenda imagens ou acerte a tarefa.
