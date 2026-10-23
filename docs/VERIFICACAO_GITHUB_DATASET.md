# Verificação da base publicada — 23/10/2026

Repositório: [YuuriSato/LLM---ODONTO](https://github.com/YuuriSato/LLM---ODONTO).
Referência consultada antes deste PR: `dca27620164f500c57e561fa0e8fed1ea9a35e0b`.
As branches remotas main e impossivel-avaliar apontavam para esse commit;
react-sato-company apontava para a4f003a. Nenhuma trouxe nova base em relação ao checkout.

## O conjunto de 103 imagens

[DATASET_INTEGRITY.md](https://github.com/YuuriSato/LLM---ODONTO/blob/dca27620164f500c57e561fa0e8fed1ea9a35e0b/docs/DATASET_INTEGRITY.md)
documenta 100 fotos AlphaDent aguardando revisão, duas edições por IA e uma imagem
sintética. Registra 94 amostras reservadas para calibração e nove para teste.
Reserva para teste não comprova execução nem rótulo correto. O próprio documento
informa que nenhum ganho de acurácia foi comprovado. O manifesto e as imagens desse
conjunto ficam em runtime/datasets, fora do Git, e não acompanham este checkout.

## Resultados efetivamente versionados

- `reports/resultado_analise_downloads.csv` e `reports/testes_downloads_medgemma.json`:
  seis análises, sem coluna de verdade de referência verificada.
- `reports/xray_patient_comparison_test.csv`: cinco comparações radiográficas.
- `reports/xray_patient_comparison_manifest_test.csv`: uma comparação.
- O conjunto legado em data contém milhares de arquivos e variantes; a quantidade
  de arquivos não é evidência de avaliação de autenticidade com rótulos verificados.

Não foi encontrada nas branches e nos relatórios consultados uma atualização com
mais de 100 imagens avaliadas como verdadeiras/falsas contra rótulos confirmados.
É necessário recuperar o manifesto e os registros da máquina que produziu a base
de 103 imagens para auditar sua situação atual.

## Validação deste PR

- Suíte Python: 141 testes, três ignorados, sem falhas.
- Ambiente neural: 13 testes, sem falhas.
- Build TypeScript/Vite e smoke UI: 25 verificações de página/viewport e fluxos de análise passaram.
- Treinamento neural odontológico e acurácia forense permanecem não validados;
  os checkpoints geométricos são exclusivamente testes de engenharia.
