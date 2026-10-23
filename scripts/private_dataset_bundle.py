"""Export and import private image collections without putting them in Git."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.history_store import HistoryStore


def digest(path: Path) -> str:
    sha = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            sha.update(chunk)
    return sha.hexdigest()


def safe_file(root: Path, name: str) -> Path:
    candidate = (root / name).resolve()
    if candidate == root.resolve() or root.resolve() not in candidate.parents or not candidate.is_file():
        raise ValueError(f"Arquivo ausente ou fora da pasta esperada: {name}")
    return candidate


def read_manifest(path: Path) -> dict:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict) or not isinstance(manifest.get("samples"), list):
        raise ValueError("Manifesto invalido")
    ids = set()
    for sample in manifest["samples"]:
        if not isinstance(sample, dict) or not isinstance(sample.get("id"), str) or sample["id"] in ids:
            raise ValueError("ID de amostra invalido ou duplicado")
        ids.add(sample["id"])
        if not isinstance(sample.get("file"), str) or not isinstance(sample.get("sha256"), str):
            raise ValueError("Imagem ou hash ausente no manifesto")
    return manifest


def export_bundle(project: Path, output: Path) -> dict:
    if project.resolve() == output.resolve() or project.resolve() in output.resolve().parents:
        raise ValueError("O pacote privado deve ficar fora do repositorio publico")
    if output.exists():
        raise FileExistsError(f"Destino ja existe: {output}")
    runtime = project / "runtime"
    source_manifest = runtime / "datasets" / "manifest.json"
    manifest = read_manifest(source_manifest)
    history = HistoryStore(runtime / "analysis_history.sqlite3", runtime / "analysis_history.json").all()
    files: dict[str, str] = {}
    planned: dict[str, Path] = {}

    def include(category: str, name: str) -> None:
        root = runtime / ("datasets" if category == "dataset" else "uploads")
        path = safe_file(root, name)
        key = f"{category}/{name}"
        files[key] = digest(path)
        planned[key] = path

    for sample in manifest["samples"]:
        for field in ("file", "reference", "provenance_artifact"):
            if sample.get(field):
                include("dataset", sample[field])
        if files[f"dataset/{sample['file']}"] != sample["sha256"]:
            raise ValueError(f"Hash de amostra divergente: {sample['id']}")
        if sample.get("reference") and files[f"dataset/{sample['reference']}"] != sample.get("reference_sha256"):
            raise ValueError(f"Hash de referencia divergente: {sample['id']}")
        if sample.get("provenance_artifact") and files[f"dataset/{sample['provenance_artifact']}"] != sample.get("provenance_sha256"):
            raise ValueError(f"Hash de procedencia divergente: {sample['id']}")
    for entry in history:
        for field in ("stored_filename", "original_stored_filename"):
            if entry.get(field):
                include("upload", entry[field])

    output.mkdir(parents=True)
    try:
        for key, path in planned.items():
            target = output / "files" / key
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, target)
            if digest(target) != files[key]:
                raise ValueError(f"Falha ao copiar: {key}")
        (output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        (output / "history.json").write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")
        index = {"schema_version": "1.0", "files": files, "samples": len(manifest["samples"]),
                 "history_records": len(history), "training_policy": "verified-development-only"}
        (output / "index.json").write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
        return index
    except Exception:
        shutil.rmtree(output)
        raise


def verify_bundle(bundle: Path) -> tuple[dict, dict, list[dict]]:
    index = json.loads((bundle / "index.json").read_text(encoding="utf-8"))
    if index.get("schema_version") != "1.0" or not isinstance(index.get("files"), dict):
        raise ValueError("Indice do pacote invalido")
    for key, expected in index["files"].items():
        if not key.startswith(("dataset/", "upload/")) or len(expected) != 64:
            raise ValueError(f"Entrada invalida: {key}")
        if digest(safe_file(bundle / "files", key)) != expected:
            raise ValueError(f"Hash divergente: {key}")
    manifest = read_manifest(bundle / "manifest.json")
    history = json.loads((bundle / "history.json").read_text(encoding="utf-8"))
    if not isinstance(history, list) or len(history) != index["history_records"]:
        raise ValueError("Historico invalido")
    if len(manifest.get("samples", [])) != index["samples"]:
        raise ValueError("Manifesto invalido")
    for sample in manifest["samples"]:
        for field in ("file", "reference", "provenance_artifact"):
            if sample.get(field) and f"dataset/{sample[field]}" not in index["files"]:
                raise ValueError(f"Imagem ausente do indice: {field}")
        if index["files"][f"dataset/{sample['file']}"] != sample["sha256"]:
            raise ValueError(f"Hash de amostra divergente: {sample['id']}")
        for field, sha_field in (("reference", "reference_sha256"),
                                 ("provenance_artifact", "provenance_sha256")):
            if sample.get(field) and index["files"][f"dataset/{sample[field]}"] != sample.get(sha_field):
                raise ValueError(f"Hash de {field} divergente: {sample['id']}")
    for entry in history:
        for field in ("stored_filename", "original_stored_filename"):
            if entry.get(field) and f"upload/{entry[field]}" not in index["files"]:
                raise ValueError(f"Imagem do historico ausente: {field}")
    return index, manifest, history


def import_bundle(project: Path, bundle: Path) -> dict:
    index, manifest, history = verify_bundle(bundle)
    runtime = project / "runtime"
    destination_manifest = runtime / "datasets" / "manifest.json"
    if destination_manifest.exists():
        existing = read_manifest(destination_manifest)
    else:
        existing = {"schema_version": manifest["schema_version"], "samples": []}
    by_id = {sample["id"]: sample for sample in existing["samples"]}
    for sample in manifest["samples"]:
        old = by_id.get(sample["id"])
        if old is not None and old != sample:
            raise ValueError(f"ID de amostra em conflito: {sample['id']}")
        by_id[sample["id"]] = sample
    store = HistoryStore(runtime / "analysis_history.sqlite3", runtime / "analysis_history.json")
    old_history = {entry["id"]: entry for entry in store.all()}
    for entry in history:
        old = old_history.get(entry["id"])
        if old is not None and old != entry:
            raise ValueError(f"ID de historico em conflito: {entry['id']}")
    for key, expected in index["files"].items():
        category, name = key.split("/", 1)
        root = runtime / ("datasets" if category == "dataset" else "uploads")
        target = (root / name).resolve()
        if root.resolve() not in target.parents:
            raise ValueError(f"Destino invalido: {key}")
        if target.exists() and digest(target) != expected:
            raise ValueError(f"Arquivo existente em conflito: {key}")
    for key in index["files"]:
        category, name = key.split("/", 1)
        target = runtime / ("datasets" if category == "dataset" else "uploads") / name
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            shutil.copyfile(safe_file(bundle / "files", key), target)
    merged = {"schema_version": manifest["schema_version"], "samples": list(by_id.values())}
    staging = destination_manifest.with_suffix(".importing.json")
    staging.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        read_manifest(staging)
        staging.replace(destination_manifest)
    finally:
        staging.unlink(missing_ok=True)
    store.upsert_all([entry for entry in history if entry["id"] not in old_history])
    return {"samples": len(manifest["samples"]), "history_records": len(history), "files": len(index["files"])}


def training_candidates(bundle: Path, output: Path) -> int:
    _, manifest, _ = verify_bundle(bundle)
    eligible = [sample for sample in manifest["samples"]
                if sample.get("verified") is True and sample.get("split") == "development"
                and sample.get("ground_truth") in {"REAL", "IA_GERADA", "IA_EDITADA", "EDICAO_TRADICIONAL"}]
    if output.exists():
        raise FileExistsError(f"Destino ja existe: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as stream:
        for sample in eligible:
            row = {"image": f"files/dataset/{sample['file']}", "label": sample["ground_truth"],
                   "group": sample["group"], "provenance": sample["provenance"]}
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")
    return len(eligible)


def main() -> None:
    parser = argparse.ArgumentParser(description="Pacote privado de imagens; nao envie ao repositorio publico.")
    parser.add_argument("action", choices=["export", "verify", "import", "train-candidates"])
    parser.add_argument("bundle", type=Path)
    parser.add_argument("--project", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    if args.action == "export":
        result = export_bundle(args.project, args.bundle)
    elif args.action == "verify":
        result = verify_bundle(args.bundle)[0]
    elif args.action == "train-candidates":
        result = {"training_candidates": training_candidates(args.bundle, args.bundle / "train_candidates.jsonl")}
    else:
        result = import_bundle(args.project, args.bundle)
    print(json.dumps({key: value for key, value in result.items() if key != "files"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
