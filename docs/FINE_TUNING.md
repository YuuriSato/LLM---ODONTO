# Fine-Tuning LoRA do MedGemma

Este guia descreve o fluxo local. Nesta máquina, o MedGemma 1.5 4B foi carregado com QLoRA em NF4 de 4 bits numa GTX 1660 SUPER de 6 GiB; o treino exige liberar VRAM antes de iniciar. O ambiente fica separado em `.venv-finetune`.

## Dataset

Organize as imagens em:

```text
data/dataset_dental/
  real/
  alterada_manualmente/
  alterada_digitalmente/
  ia/
  indeterminado/
```

Gere o JSONL:

```powershell
.\.venv\Scripts\python.exe .\scripts\training\prepare_training_jsonl.py
```

Saida padrao:

```text
data/codex_training.jsonl
```

## Dependências e acesso aos pesos

```powershell
.\.venv-finetune\Scripts\python.exe -m pip install torch torchvision --index-url https://download.pytorch.org/whl/cu128
.\.venv-finetune\Scripts\python.exe -m pip install peft accelerate bitsandbytes "transformers>=4.50,<5" sentencepiece
```

Para Hugging Face:

```powershell
.\.venv\Scripts\hf.exe auth login
```

Aceite os termos na página do MedGemma usando a mesma conta do Hugging Face antes do login. O token não deve ser salvo em `.env`, nem enviado ao repositório.

## Treino QLoRA local

Com GPU, use os mesmos caminhos do projeto:

```powershell
.\.venv-finetune\Scripts\python.exe scripts\training\finetune_lora_medgemma.py `
  --model-id google/medgemma-1.5-4b-it `
  --dataset-jsonl data/codex_training.jsonl `
  --image-root data/dataset_dental `
  --output-dir runtime/outputs/medgemma-dental-lora `
  --load-in-4bit `
  --gradient-checkpointing `
  --epochs 2 `
  --batch-size 1 `
  --grad-accum 8 `
  --max-length 512
```

O script salva checkpoints por época e escreve `dashboard-progress.json` a cada log para execuções iniciadas com a versão atual. Não inicie mais de um treino simultâneo na GPU de 6 GiB.

## Execução registrada em 23–24/10/2026

`runtime/outputs/medgemma-dental-lora/` contém um adaptador LoRA concluído: 476 passos, 2 épocas, perda média de treino 0,03025 e adaptador salvo. A execução usa o JSONL legado de 1.902 itens. Ela demonstra que o treinamento e o salvamento do adaptador funcionam, mas não prova desempenho odontológico ou forense: o conjunto não tem divisão independente documentada, não contém a classe IA e seus rótulos ainda precisam de auditoria. Consulte `docs/MODEL_CARD_MEDGEMMA_DENTAL_LORA.md` antes de usar o adaptador.

## Merge/Exportacao

```bash
python scripts/training/merge_lora.py \
  --base google/medgemma-1.5-4b-it \
  --adapter runtime/outputs/medgemma-dental-lora \
  --output runtime/outputs/medgemma-dental-merged
```

Conversao para GGUF/Ollama depende de suporte atualizado do `llama.cpp` para a arquitetura usada.

## Observacoes

- Ollama e usado para inferencia; o treino deve ocorrer fora dele.
- A qualidade depende do dataset: use pares reais/falsos parecidos com seu caso.
- Para detectar IA em fotos intraorais, inclua exemplos reais com reflexos/saliva/metal e falsos com dentes reconstruidos por IA.
