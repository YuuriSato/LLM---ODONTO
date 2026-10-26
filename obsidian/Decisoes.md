---
tags: [lm-odonto, decisoes]
---

# Decisões

[[Inicio]] · [[Qualidade e contradicoes]] · [[Dataset]] · [[Rede neural]]

1. Preservar original, medições e respostas para rastrear conclusões.
2. Corrigir contradições antes de ajustar limiares de qualidade ou treinar um novo modelo.
3. Não transformar ausência de anomalia em autenticação.
4. Não tratar metadados ausentes ou detector desativado como evidência de fraude.
5. Isolar dependências neurais em `.venv-neural` para não afetar o serviço web.
6. Treinar somente com rótulos explicitamente verificados; usar dados sintéticos geométricos para testes de engenharia.
7. Exportar ao cofre apenas resumos agregados por padrão, preservando notas manuais.

Decisões futuras devem registrar motivo, evidências, riscos e critério de avaliação.
