---
tags: [lm-odonto, aprendizado]
---

# Rede neural

[[Inicio]] · [[Dataset]] · [[Validacao]] · [[Arquitetura]]

A implementação inicial está em `app/neural/`. É uma CNN compacta em PyTorch com três blocos convolucionais e uma cabeça classificadora. O processamento preserva proporção por preenchimento, normaliza pixels e usa 192 × 192. Essa redução é uma escolha experimental que precisa ser comparada a alternativas para adulterações sutis.

Treino: `scripts/training/train_neural.py`. Predição: `scripts/training/predict_neural.py`. Cada execução salva configuração, manifesto, histórico por época, pesos e matriz de confusão. O nome da pasta não pode ser reutilizado, evitando substituir resultados antigos.

O teste de engenharia usa padrões geométricos para verificar aprendizado, salvamento e leitura. Ele não treina um detector odontológico. Os modelos treinados produzem softmax não calibrado. A integração com vereditos requer validação específica; não usar pontuação como probabilidade de autenticidade.

Instruções completas em `../fine_tuning/REDE_NEURAL.md`.
