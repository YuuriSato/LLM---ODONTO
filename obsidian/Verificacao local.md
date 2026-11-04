---
tags: [lm-odonto, verificacao]
---

# Verificação local — 22/10/2026

[[Inicio]] · [[Dataset]] · [[Rede neural]] · [[Qualidade e contradicoes]]

## Evidência disponível

- Inventário: 3.254 arquivos, 1.386 hashes distintos, 1.868 cópias duplicadas; nenhum erro de leitura. Os originais foram preservados.
- A revisão de procedência ainda não aprovou imagens. Os nomes das pastas são candidatos a rótulo, não comprovação.
- O teste do construtor de dataset cobre a cópia de amostras revisadas das quatro classes nas três partições e a validação do manifesto resultante.
- Ambiente neural: 11 testes passaram, incluindo manifesto, inventário e carregamento do modelo.
- Suíte principal: 135 testes executados, 3 ignorados, sem falhas. Os testes neurais foram executados separadamente no ambiente com PyTorch.
- Todos os links internos destas notas apontam para notas existentes.

## Experimento com LM Studio

Na execução `5260edc7caf24ae5a174592a6c6dc03a`, usando MedGemma local e a fotografia de 797 × 1.077, a identificação visual continuou contraditória após duas tentativas. A execução terminou com `inconsistent_model_output`, sem veredito. Resultado detalhado local em `../runtime/evaluations/visual-intake-v2/5260edc7caf24ae5a174592a6c6dc03a/result.json`.

Isso comprova o bloqueio dessa resposta incoerente, não a capacidade de autenticar a imagem. A checagem textual reconhece expressões específicas; não cobre toda contradição possível.

## Próximos requisitos

1. Revisar procedência e grupos do inventário existente, priorizando conteúdos únicos.
2. Identificar quais classes têm comprovação e quais precisam de novas amostras.
3. Treinar e avaliar a CNN em imagens odontológicas verificadas, com grupos independentes.
4. Avaliar os erros do modelo visual em um conjunto representativo, além deste caso.

O treinamento com padrões geométricos confirma o funcionamento técnico da rede, mas não satisfaz a validação odontológica.
