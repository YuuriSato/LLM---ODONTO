"""Export direct developer feedback to a private, conflict-filtered JSONL."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from app.history_store import HistoryStore


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime", type=Path, default=Path("runtime"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists():
        raise FileExistsError(output)
    if not output.is_relative_to(args.runtime.resolve()):
        raise ValueError("O JSONL de feedback deve permanecer em runtime/ privado.")

    entries = HistoryStore(args.runtime / "analysis_history.sqlite3",
                           args.runtime / "analysis_history.json").all()
    by_hash: dict[str, list[dict]] = defaultdict(list)
    for entry in entries:
        if not str(entry.get("source", "")).startswith("feedback_usuario"):
            continue
        name = entry.get("stored_filename")
        if not name:
            continue
        image = (args.runtime / "uploads" / name).resolve()
        if not image.is_relative_to((args.runtime / "uploads").resolve()) or not image.is_file():
            continue
        by_hash[hashlib.sha256(image.read_bytes()).hexdigest()].append(entry)

    manifest = json.loads((args.runtime / "datasets" / "manifest.json").read_text(encoding="utf-8"))
    held_out = {sample["sha256"].lower() for sample in manifest["samples"]
                if sample.get("split") == "test"}
    records, excluded = [], []
    for sha256, group in sorted(by_hash.items()):
        labels = {entry.get("verdict") for entry in group}
        if len(labels) != 1 or sha256 in held_out:
            excluded.append({"sha256": sha256, "reason": "conflicting_labels" if len(labels) != 1 else "held_out_test",
                             "labels": sorted(str(label) for label in labels)})
            continue
        label = next(iter(labels))
        if label not in {"REAL", "MODIFICADO", "IA_GERADA_EDITADA"}:
            excluded.append({"sha256": sha256, "reason": "unsupported_label", "labels": [str(label)]})
            continue
        entry = max(group, key=lambda item: str(item.get("created_at", "")))
        records.append({"image": entry["stored_filename"], "label": label,
                        "evidence": "Marcacao informada pelo desenvolvedor; procedencia independente nao comprovada.",
                        "prompt": "Classifique a imagem odontologica como REAL, MODIFICADO ou IA_GERADA_EDITADA. Responda apenas VEREDITO: <classe>.",
                        "answer": f"VEREDITO: {label}"})

    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as stream:
        for record in records:
            stream.write(json.dumps(record, ensure_ascii=False) + "\n")
    report = {"direct_feedback_records": sum(map(len, by_hash.values())),
              "unique_hashes": len(by_hash), "included": len(records),
              "labels": dict(Counter(record["label"] for record in records)),
              "excluded": excluded, "policy": "developer_feedback_only_no_independent_accuracy_claim"}
    output.with_suffix(".audit.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({key: value for key, value in report.items() if key != "excluded"}, ensure_ascii=False))
    print(f"excluded_count={len(excluded)}")


if __name__ == "__main__":
    main()
