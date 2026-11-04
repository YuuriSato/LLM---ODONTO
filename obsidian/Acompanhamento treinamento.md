# Acompanhamento do treinamento

[[Inicio]] · [[Dataset]] · [[Rede neural]] · [[Validacao]]

## 23/10/2026

O código do PR #4 foi incorporado à branch do PR #3, preservando seu commit como ancestral. Main não foi alterada. O pacote privado de 104 amostras/125 registros continua ausente: `runtime/datasets/manifest.json` não existe neste checkout. A descrição remota do PR #4 ainda informa que a transferência está pendente.

O CI anterior passou no frontend e no backend Ubuntu. No Windows, um teste comparava o caminho temporário abreviado RUNNER~1 com o caminho resolvido runneradmin. A asserção foi corrigida para comparar caminhos resolvidos; não houve alteração do avaliador para contornar o teste.

O treinamento MedGemma não foi iniciado, e nenhum GGUF treinado foi produzido. A máquina apresenta uma GTX 1660 SUPER; capacidade de treinamento, acesso aos pesos completos e suporte de exportação multimodal precisam de validação específica antes de iniciar. O checkpoint da CNN geométrica não substitui esse treinamento.

Próxima dependência concreta: receber o pacote privado e verificar procedência, rótulos e grupos, mantendo amostras de teste fora do treino. O fluxo de importação está documentado em `../docs/PRIVATE_DATASET_SYNC.md`.

## 26/10/2026 — exportação GGUF

O pacote privado foi posteriormente importado, e o treino LoRA MedGemma 1.5 terminou em 476 passos. A exportação local fundiu o adaptador ao modelo base, gerou um GGUF Q4_K_M e um projetor visual separado em `../fine_tuning/exports/medgemma-1.5-4b-it/2026-10-24-lora/`. O LM Studio carregou `medgemma-dental-lora-1.5`, reconheceu visão e respondeu a uma imagem pela API local. Os arquivos de pesos e o manifesto com hashes permanecem fora do Git.

O resultado é **experimental**: a mesma resposta apareceu num controle sem imagem, e o teste multimodal direto gerou texto repetitivo. A exportação funciona tecnicamente, mas ainda não comprova que o modelo usa a imagem nem que classifica autenticidade corretamente. [[Validacao]] continua necessária antes de qualquer conclusão sobre desempenho.

## 03/11/2026 — continuação com marcações do desenvolvedor

O histórico privado preservou 21 marcações diretas para 16 imagens distintas. Após agrupar por hash, uma imagem com três rótulos conflitantes foi excluída. O novo conjunto privado contém 15 imagens: 9 marcadas `IA_GERADA_EDITADA`, 4 `REAL` e 2 `MODIFICADO`. O script de preparação bloqueia hashes reservados no teste do manifesto. Não promove marcações do operador automaticamente a procedência verificada.

Um novo treino QLoRA de uma época terminou em 15 passos, partindo do adaptador anterior e salvando em `../runtime/outputs/medgemma-dental-lora-feedback-20261103/`. Os pesos mudaram e são finitos. O log mostra norma de gradiente indefinida nos seis primeiros passos e finita nos restantes. A perda média de treino foi 1,3865. Esta execução não possui avaliação independente e ainda não foi exportada para GGUF nem instalada no LM Studio. Consulte `../docs/MODEL_CARD_MEDGEMMA_DENTAL_LORA.md`.

## 03/11/2026 — novo treino com 1.917 imagens

O primeiro conjunto privado combinou 1.902 registros legados e 15 marcações diretas sem conflito. Embora tivesse 1.917 caminhos diferentes, uma auditoria por conteúdo encontrou 516 duplicatas exatas, quase todas `REAL`. A primeira tentativa foi interrompida antes do primeiro passo, preservando seus logs. O conjunto corrigido contém 1.401 imagens únicas em `../runtime/combined-deduplicated-20261103/`, ignorado pelo Git. A distribuição por classe e o hash estão no [[../docs/MODEL_CARD_MEDGEMMA_DENTAL_LORA|cartão do modelo]].

O treino corrigido partiu do adaptador de feedback, com QLoRA NF4, uma época e 176 passos de otimização. Os arquivos ficam em `../runtime/outputs/medgemma-dental-lora-deduplicated-20261103/`, com salvamento a cada 25 passos e retenção dos dois checkpoints mais recentes.

## 04/11/2026 — conclusão da nova execução

`trainer_state.json` confirma 176 passos; `train_results.json` registra uma época, 44.188 segundos e perda média de treino 0,004195. O adaptador final (SHA-256 `1c7b63def6b12c06f091792437d4d114e5ae84227a8da610057acf13f70ff062`) contém 476 tensores LoRA finitos, todos diferentes do adaptador inicial. Os checkpoints 175 e 176 foram preservados. Isto comprova a execução e o salvamento dos pesos, mas não qualidade de classificação. Ainda não há teste independente nem exportação GGUF deste adaptador. Consulte o [[../docs/MODEL_CARD_MEDGEMMA_DENTAL_LORA|cartão do modelo]].
