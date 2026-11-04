import json
from pathlib import Path
import tempfile
import unittest
from app.neural.dataset import read_manifest, digest


class NeuralManifestTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.manifest = {'schema_version': '1.0', 'scope': 'engineering', 'classes': ['A', 'B'], 'samples': []}
        for split in ('train', 'validation', 'test'):
            for label in ('A', 'B'):
                name = f'{split}-{label}'
                path = self.root / name
                path.write_bytes(name.encode())
                self.manifest['samples'].append({'id': name, 'file': name, 'group': name, 'label': label,
                    'split': split, 'verified': True, 'provenance': 'Unit fixture', 'sha256': digest(path)})
        self.path = self.root / 'manifest.json'

    def read(self):
        self.path.write_text(json.dumps(self.manifest), encoding='utf-8')
        return read_manifest(self.path)

    def test_group_leakage_is_rejected(self):
        self.manifest['samples'][2]['group'] = self.manifest['samples'][0]['group']
        with self.assertRaisesRegex(ValueError, 'Vazamento'):
            self.read()

    def test_changed_content_is_rejected(self):
        (self.root / self.manifest['samples'][0]['file']).write_text('modified')
        with self.assertRaisesRegex(ValueError, 'Hash'):
            self.read()

    def test_unverified_label_is_rejected(self):
        self.manifest['samples'][0]['verified'] = False
        with self.assertRaisesRegex(ValueError, 'verificada'):
            self.read()

    def test_external_path_is_rejected(self):
        self.manifest['samples'][0]['file'] = '../outside.png'
        with self.assertRaisesRegex(ValueError, 'fora'):
            self.read()

    def test_duplicate_image_rejected_even_with_another_id(self):
        self.manifest['samples'][1].update(file=self.manifest['samples'][0]['file'], sha256=self.manifest['samples'][0]['sha256'])
        with self.assertRaisesRegex(ValueError, 'duplicada'):
            self.read()

    def test_valid_manifest(self):
        self.assertEqual(len(self.read()['samples']), 6)
