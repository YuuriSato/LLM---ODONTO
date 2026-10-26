"""Merge a local MedGemma PEFT adapter into its exact base model on CPU.

This produces intermediate Hugging Face weights for a later GGUF conversion.
Keep the output in an ignored, private directory; the merged weights are not
validated merely because the merge succeeds.
"""
from __future__ import annotations

import argparse
import gc
import json
from pathlib import Path

import torch
from peft import PeftModel
from transformers import AutoModelForImageTextToText, AutoProcessor


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, required=True, help="Local MedGemma base snapshot")
    parser.add_argument("--adapter", type=Path, required=True, help="Local PEFT adapter")
    parser.add_argument("--output", type=Path, required=True, help="Private HF output directory")
    args = parser.parse_args()

    config_path = args.adapter / "adapter_config.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    if config.get("base_model_name_or_path") != "google/medgemma-1.5-4b-it":
        raise ValueError("O adaptador não corresponde ao MedGemma 1.5 4B esperado.")
    if not (args.base / "config.json").is_file():
        raise FileNotFoundError("Snapshot base sem config.json")
    base_config = json.loads((args.base / "config.json").read_text(encoding="utf-8"))
    if base_config.get("model_type") != "gemma3":
        raise ValueError("O snapshot base não é Gemma 3/MedGemma 1.5.")
    if args.output.exists() and any(args.output.iterdir()):
        raise FileExistsError("A saída já contém arquivos; use outra pasta para preservar artefatos.")
    args.output.mkdir(parents=True, exist_ok=True)

    model = AutoModelForImageTextToText.from_pretrained(
        args.base,
        dtype=torch.bfloat16,
        low_cpu_mem_usage=True,
        local_files_only=True,
    )
    if any(parameter.device.type == "meta" for parameter in model.parameters()):
        raise RuntimeError("Pesos base permanecem em meta device; fusão cancelada.")
    adapted = PeftModel.from_pretrained(model, args.adapter, is_trainable=False)
    merged = adapted.merge_and_unload(safe_merge=True)
    del adapted, model
    gc.collect()
    merged.save_pretrained(args.output, safe_serialization=True, max_shard_size="2GB")
    processor = AutoProcessor.from_pretrained(args.base, local_files_only=True)
    processor.save_pretrained(args.output)
    print(f"Merged HF model written to {args.output}", flush=True)


if __name__ == "__main__":
    main()
