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
