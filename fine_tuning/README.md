# Fine-tuning

Área para novos experimentos. Os scripts existentes continuam em `../scripts/training/` e o guia original está em `../docs/FINE_TUNING.md`.

Estrutura local:

- `datasets/`: manifests e datasets de novos experimentos.
- `runs/`: checkpoints, adaptadores e métricas de cada execução.
- `exports/`: modelos exportados.

Essas três pastas são ignoradas pelo Git. A configuração inicial não executou treino. Na etapa seguinte foram executados testes de treino de uma CNN com padrões geométricos, sem validação odontológica. Consulte [Rede neural](REDE_NEURAL.md).

Antes de treinar, revise procedência, rótulos e separação entre treino e teste. O JSONL legado não contém exemplos da classe IA e não deve ser confundido com validação do detector atual.

Veja `HISTORICO.md` para a auditoria do material recebido.
