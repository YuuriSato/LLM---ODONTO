# Levantamento de fine-tuning — 22/10/2026

Origem: https://github.com/YuuriSato/LLM---ODONTO.git

Branch instalada: `main`, commit `dca27620164f500c57e561fa0e8fed1ea9a35e0b`.

## Conclusão

Há preparação e relato de tentativa de fine-tuning, mas não há evidência versionada de um treinamento concluído. `docs/FINE_TUNING.md:3` e `README.md:439` informam que o treino do MedGemma 1.5 4B em CPU não foi viável na máquina de origem. Isso não é uma avaliação do hardware desta máquina.

## Material existente

- `scripts/training/prepare_training_jsonl.py`: preparação do dataset.
- `scripts/training/synthesize_training_variants.py`: variantes sintéticas.
- `scripts/training/finetune_lora_medgemma.py`: treinamento LoRA/QLoRA, opções CPU/GPU.
- `scripts/training/merge_lora.py`: merge do adaptador com o modelo base.
- `requirements-finetune.txt` e `requirements-finetune-cpu.txt`: dependências específicas de treino.
- `data/codex_training.jsonl`: 1.902 registros JSON válidos: REAL 1.352; ALTERADA_MANUALMENTE 250; ALTERADA_DIGITALMENTE 250; INDETERMINADO 50; IA 0.
- Todas as 1.902 referências de imagem desse JSONL existem em `data/dataset_dental/` no checkout recebido.
- `models/Modelfile-Codex-Dental` usa `FROM medgemma1.5:4b` com parâmetros e prompt de sistema. Isso configura inferência e não comprova ajuste dos pesos.
- `reports/resultado_analise_downloads.md:19` declara que as análises foram feitas com o modelo base, sem fine-tuning específico.
- `docs/IMPROVEMENT_CHECKLIST.md:87` registra ausência de fine-tuning e de melhora comprovada no trabalho descrito.

## Histórico Git e limites

O commit `d5f5a51` (Project tree) adicionou os quatro scripts, o guia e o JSONL. Foram consultados o histórico Git disponível e as árvores das branches remotas `main`, `impossivel-avaliar` e `react-sato-company`. Não foram localizados arquivos de adaptador, checkpoints, `trainer_state`, pesos safetensors ou logs versionados de treinamento.

`logs/` e `runtime/outputs/` estão no `.gitignore` original. Portanto, poderiam existir resultados privados na máquina anterior que não vieram pelo Git. A ausência desses arquivos no repositório não prova que nenhuma execução aconteceu fora dele.

O pipeline atual descrito no README usa perícia local e Gemini; os scripts de treinamento são documentados como legado experimental. Não se iniciou treinamento nem se baixaram pesos nesta instalação.
