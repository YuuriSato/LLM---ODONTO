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

## Continuação com feedback do desenvolvedor — 03/11/2026

As marcações diretas do histórico foram reconciliadas por SHA-256: 21 registros apontavam para 16 imagens distintas. Uma imagem recebeu três rótulos conflitantes e foi excluída. Quinze imagens entraram na nova execução privada: 9 `IA_GERADA_EDITADA`, 4 `REAL` e 2 `MODIFICADO`. Amostras reservadas no manifesto como teste foram bloqueadas. O script `scripts/training/prepare_developer_feedback.py` gerou o JSONL privado e um relatório de exclusões em `runtime/feedback-training-20261103/`.

O adaptador anterior foi continuado em `runtime/outputs/medgemma-dental-lora-feedback-20261103/` com QLoRA NF4, uma época, 15 passos, taxa de aprendizado `1e-5`, batch 1 e gradient checkpointing. A perda média registrada foi 1,3865. Os 476 tensores do novo adaptador diferem dos anteriores e são finitos. Os seis primeiros passos registraram `grad_norm=nan`; os seguintes tiveram norma finita. O log e os parâmetros ficam na pasta privada da execução.

Estas marcações representam feedback do operador, sem confirmação independente de procedência. Não houve conjunto de teste independente para esta execução nem comparação de acurácia com o adaptador anterior. O GGUF instalado e o serviço Sato Company **não foram substituídos** por este novo adaptador. A validação deve anteceder qualquer atualização do modelo operacional.

## Nova execução com o acervo combinado — 03/11/2026

O conjunto inicial tinha 1.917 registros, mas uma auditoria por SHA-256 das imagens encontrou 516 cópias exatas, sem conflitos de rótulo. A primeira execução foi interrompida antes de concluir o primeiro passo, e seus logs foram preservados em `runtime/outputs/medgemma-dental-lora-combined-20261103/`. O novo conjunto privado contém 1.401 imagens únicas: 841 `REAL`, 250 `ALTERADA_MANUALMENTE`, 250 `ALTERADA_DIGITALMENTE`, 49 `INDETERMINADO`, 9 `IA_GERADA_EDITADA` e 2 `MODIFICADO`. O manifesto em `runtime/combined-deduplicated-20261103/` registra SHA-256 `1e267b6135d5f0faf2d0fa5905f504ed56824c1709935c984e0e71e78a580c71`. As imagens, os logs e os pesos ficam fora do Git.

Parâmetros da nova execução: MedGemma 1.5 4B, adaptador inicial com feedback, QLoRA NF4, uma época, batch 1, acumulação de gradientes 8, taxa `1e-5`, comprimento máximo 512, checkpoints a cada 25 passos de otimização e retenção dos dois últimos. A previsão é de 176 passos; o diretório privado é `runtime/outputs/medgemma-dental-lora-deduplicated-20261103/`. O processo foi iniciado, mas esta entrada **não comprova conclusão do treino**. Não há conjunto de validação/teste independente. As etiquetas do acervo legado e o feedback do operador não têm confirmação independente de procedência; por isso nenhuma acurácia pode ser declarada.
