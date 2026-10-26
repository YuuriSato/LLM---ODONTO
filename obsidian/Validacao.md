---
tags: [lm-odonto, testes]
---

# Validação

[[Inicio]] · [[Qualidade e contradicoes]] · [[Dataset]] · [[Rede neural]]

Os testes de software comprovam contratos e comportamentos cobertos por seus casos. A acurácia odontológica exige dados independentes de procedência conhecida.

Medir: acerto de modalidade, coerência das justificativas, cobertura das decisões, erro entre decisões aceitas, falsos positivos de IA, falhas técnicas, abstenções justificadas, latência e repetibilidade.

Manter os estados distintos: análise concluída, inconclusiva, impossível de avaliar, falha técnica e resposta contraditória. Não melhorar cobertura escondendo falhas ou forçando REAL.

Comandos, na raiz:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py"
npm run build
npm run test:ui
.\.venv\Scripts\python.exe scripts/check_private_files.py
```

O teste neural de engenharia usa padrões geométricos conhecidos. Seu desempenho não pode ser apresentado como precisão de detecção de IA odontológica.
