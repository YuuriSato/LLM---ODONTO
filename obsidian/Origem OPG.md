---
tags: [lm-odonto, dados, procedencia]
---

# Origem candidata do conjunto OPG

[[Dataset]] · [[Fontes]] · [[Validacao]]

Consulta em 22/10/2026: a publicação [Dental OPG XRAY Dataset, versão 4](https://data.mendeley.com/datasets/c4hhrkxytw/4), DOI 10.17632/c4hhrkxytw.4, apresenta nome e estrutura compatíveis com a cópia local. A licença indicada é CC BY 4.0. Isso identifica uma fonte candidata; a identidade dos arquivos locais com a publicação ainda não foi confirmada por hashes.

A descrição publicada informa 232 imagens originais e 604 aumentadas na área de detecção. A inspeção local de `data/fine` encontrou 231 imagens na pasta Original Dataset, 604 em Augmented Dataset e 517 em classificação. Esses são arquivos, não pacientes únicos. O total local é 1.352 JPGs e 835 TXT de anotações.

O [artigo dos autores](https://pmc.ncbi.nlm.nih.gov/articles/PMC11470401/) descreve aquisição das radiografias por câmera de telefone, processamento CLAHE e aumento dos dados. A versão 1 do repositório descreve operações como rotação e espelhamento. Nenhuma dessas descrições constitui um rótulo forense individual para os arquivos locais.

## Consequência para o treinamento

A pasta local `real` mistura originais, classificação e exemplos aumentados. Não usar a pasta inteira como classe REAL verificada. É necessário definir se REAL significa aquisição sem geração por IA ou ausência de edição: imagens aumentadas podem ter origem clínica e, ao mesmo tempo, transformações tradicionais. O projeto prevê EDICAO_TRADICIONAL separadamente, portanto essa ambiguidade precisa ser resolvida antes da rotulagem.

Também é necessário ligar as imagens aumentadas aos seus originais e manter o mesmo paciente/original em uma única partição. A divisão publicada para detecção não é automaticamente adequada à avaliação forense.

Metadados públicos da versão 4 foram preservados em `../fine_tuning/datasets/legacy-review-v1/source-mendeley-v4.json`. A consulta de arquivos retornou lista vazia; nenhum arquivo público de imagem foi baixado ou comparado. Pendem a confirmação da fonte local, a versão usada e a explicação para a diferença de um original.
