import json
from pathlib import Path
import tempfile
import unittest

from app.history_store import HistoryStore
from scripts.private_dataset_bundle import digest, export_bundle, import_bundle, training_candidates, verify_bundle


class PrivateDatasetBundleTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.source = self.root / "source"
        datasets = self.source / "runtime" / "datasets"
        uploads = self.source / "runtime" / "uploads"
        datasets.mkdir(parents=True)
        uploads.mkdir(parents=True)
        (datasets / "sample.png").write_bytes(b"image")
        (uploads / "history.jpg").write_bytes(b"history image")
        manifest = {"schema_version": "1.1", "samples": [{"id": "one", "file": "sample.png",
                    "sha256": digest(datasets / "sample.png"), "group": "patient-one",
                    "split": "development", "ground_truth": "IA_EDITADA", "verified": True,
                    "provenance": "Known synthetic edit"}]}
        (datasets / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        HistoryStore(self.source / "runtime" / "analysis_history.sqlite3").append(
            {"id": "h1", "created_at": "2026-01-01", "stored_filename": "history.jpg"})
        self.bundle = self.root / "bundle"

    def test_roundtrip_and_training_filter(self):
        index = export_bundle(self.source, self.bundle)
        self.assertEqual(index["samples"], 1)
        self.assertEqual(index["history_records"], 1)
        verify_bundle(self.bundle)
        self.assertEqual(training_candidates(self.bundle, self.root / "candidates.jsonl"), 1)
        target = self.root / "target"
        import_bundle(target, self.bundle)
        self.assertEqual((target / "runtime" / "uploads" / "history.jpg").read_bytes(), b"history image")
        self.assertEqual(len(HistoryStore(target / "runtime" / "analysis_history.sqlite3").all()), 1)
        import_bundle(target, self.bundle)
        self.assertEqual(len(HistoryStore(target / "runtime" / "analysis_history.sqlite3").all()), 1)

    def test_tamper_is_rejected(self):
        export_bundle(self.source, self.bundle)
        (self.bundle / "files" / "upload" / "history.jpg").write_bytes(b"tampered")
        with self.assertRaisesRegex(ValueError, "Hash divergente"):
            verify_bundle(self.bundle)

    def test_unverified_is_not_training_data(self):
        manifest_path = self.source / "runtime" / "datasets" / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["samples"][0]["verified"] = False
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        export_bundle(self.source, self.bundle)
        self.assertEqual(training_candidates(self.bundle, self.root / "candidates.jsonl"), 0)

    def test_export_rejects_public_repository_path(self):
        with self.assertRaisesRegex(ValueError, "fora do repositorio"):
            export_bundle(self.source, self.source / "private-images")


if __name__ == "__main__":
    unittest.main()
