# MedGemma Dental LoRA — execução local de 23–24/10/2026

## Identificação

- Modelo base: `google/medgemma-1.5-4b-it`.
- Método: LoRA sobre o modelo de linguagem, com os pesos base carregados em NF4 de 4 bits.
- Artefato local: `runtime/outputs/medgemma-dental-lora/adapter_model.safetensors`.
- Hash SHA-256 do adaptador: `276e70a4089e1b81aaee274158c4253c5263875686de352d82128c55c7808ee3`.

## Execução registrada

A execução concluiu 476 passos em duas épocas. `train_results.json` registra perda média de treino de 0,0302524. Os pesos do adaptador existem e os tensores LoRA salvos são finitos. Isto comprova que houve otimização e salvamento de um adaptador; não mede generalização.

## Dados usados

O JSONL legado tem 1.902 exemplos: 1.352 `REAL`, 250 `ALTERADA_MANUALMENTE`, 250 `ALTERADA_DIGITALMENTE` e 50 `INDETERMINADO`. As alterações foram sintetizadas ou derivadas do acervo legado. Não há classe `IA` neste treino, nem divisão de validação/teste independente registrada para essa execução.

## Uso adequado

Use o adaptador somente para desenvolvimento e testes controlados. Antes de qualquer decisão sobre autenticidade, obtenha rótulos de referência independentes, agrupe variantes por paciente/original e reserve grupos inteiros para validação e teste. Saídas do modelo não são prova de origem, diagnóstico ou integridade de uma imagem.

## Fora de escopo

O adaptador não foi validado para fotografias intraorais, radiografias de origem desconhecida, detecção de conteúdo gerado por IA, nem uso clínico. A perda de treino não é acurácia, calibração ou confiança.

## Próxima avaliação necessária

Criar um manifesto revisado com procedência, rótulo, grupo e divisão por grupo. Só então medir métricas por classe no conjunto de teste que permaneceu inacessível durante a configuração e o treino.

## Exportação GGUF local — 26/10/2026

O adaptador foi fundido ao mesmo snapshot do `google/medgemma-1.5-4b-it` usado como base e convertido para GGUF Q4_K_M. O projetor visual foi convertido separadamente. Os arquivos ficam em `fine_tuning/exports/medgemma-1.5-4b-it/2026-10-24-lora/`, pasta ignorada pelo Git. O LM Studio carregou o modelo como `medgemma-dental-lora-1.5`, identificou capacidade visual e respondeu a uma chamada local com imagem. O cliente do projeto descobriu esse identificador entre os modelos visuais carregados.

Esse teste comprova carregamento e geração, não qualidade: um controle sem imagem produziu exatamente a mesma resposta que o teste com imagem, e a execução pelo `llama-mtmd-cli` gerou texto repetitivo. O modelo continua experimental. Não trate o veredito como evidência visual confiável até haver avaliação independente por grupos de paciente/original.
