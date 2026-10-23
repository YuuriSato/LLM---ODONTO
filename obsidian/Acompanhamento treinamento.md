# Acompanhamento do treinamento

[[Inicio]] · [[Dataset]] · [[Rede neural]] · [[Validacao]]

## 23/10/2026

O código do PR #4 foi incorporado à branch do PR #3, preservando seu commit como ancestral. Main não foi alterada. O pacote privado de 104 amostras/125 registros continua ausente: `runtime/datasets/manifest.json` não existe neste checkout. A descrição remota do PR #4 ainda informa que a transferência está pendente.

O CI anterior passou no frontend e no backend Ubuntu. No Windows, um teste comparava o caminho temporário abreviado RUNNER~1 com o caminho resolvido runneradmin. A asserção foi corrigida para comparar caminhos resolvidos; não houve alteração do avaliador para contornar o teste.

O treinamento MedGemma não foi iniciado, e nenhum GGUF treinado foi produzido. A máquina apresenta uma GTX 1660 SUPER; capacidade de treinamento, acesso aos pesos completos e suporte de exportação multimodal precisam de validação específica antes de iniciar. O checkpoint da CNN geométrica não substitui esse treinamento.

Próxima dependência concreta: receber o pacote privado e verificar procedência, rótulos e grupos, mantendo amostras de teste fora do treino. O fluxo de importação está documentado em `../docs/PRIVATE_DATASET_SYNC.md`.
