---
tags: [lm-odonto, evidencias]
---

# Qualidade e contradições

Teste ao vivo posterior: execução `5f5fd2cac9164965bc42afaf39a756d2`, em `runtime/evaluations/authenticity-v1`, deixou de sugerir originalidade pela ausência de anomalias, mas atribuiu processamento tradicional à ausência de EXIF e à qualidade geral. A auditoria 2.3 aceitou esse texto indevidamente. A versão 2.4 reconhece também essa expressão; a reaplicação à resposta salva detectou o conflito e 39 testes relacionados passaram. Não foi comprovada confiabilidade geral do modelo nem realizada nova inferência após essa última ampliação. A suíte principal anterior à ampliação executou 139 testes, com 3 ignorados e sem falhas.

Atualização de 23/10/2026: o caso salvo `d2fdd7eb560241ccb2fed5cf5c82d7c8` afirmava que ausência de anomalias sugeria originalidade. A nova auditoria reconhece essa inferência como `unsupported_authenticity_inference`, solicita revisão e rejeita a resposta se persistir. A reprodução da auditoria sobre a resposta salva confirmou a detecção; 37 testes relacionados passaram. O histórico original foi preservado. A regra reconhece expressões delimitadas, não toda paráfrase possível, e não altera os pesos do modelo.

[[Inicio]] · [[Arquitetura]] · [[Validacao]] · [[Fontes]]

Dimensões do arquivo são fatos. Qualidade global é uma heurística. Visibilidade regional depende do conteúdo. Autenticidade depende de procedência e evidências; nenhuma dessas propriedades equivale às outras.

Um caso local de 685 × 224 aciona os limites atuais. Outro, de 797 × 1.077, passa nesses limites, mas recebeu uma alegação de baixa resolução e foi chamado de radiografia apesar de mostrar fotografias. Esse segundo caso demonstra uma resposta incoerente, sem demonstrar a autenticidade da imagem.

O módulo `app/ai/consistency.py` compara bloqueios estruturados com a medição correspondente e detecta algumas alegações textuais comuns. A verificação textual é limitada: paráfrases e erros de modalidade ainda precisam de avaliação própria. Qualidade global boa não impede que uma região esteja encoberta.

Se a revisão mantém uma contradição reconhecida, a execução termina com `inconsistent_model_output` e preserva respostas e medições. Uma origem desconhecida com justificativa coerente pode permanecer inconclusiva.

No fluxo local, uma etapa visual curta identifica modalidade, painéis e descrição antes das métricas. Divergência com a análise principal exige revisão e, se persistir, invalida a resposta. Concordância entre duas chamadas do mesmo modelo não prova acerto; OUTRA permite identificação incerta. Isso é um controle de coerência, não uma autenticação independente.
