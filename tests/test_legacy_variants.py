from pathlib import Path
import random
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

from PIL import Image
from scripts.training.synthesize_training_variants import main
from scripts.training.audit_legacy_variants import audit


class LegacyAuditTests(unittest.TestCase):
    def test_exact_replay_and_tampering_without_modifying_sources(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'real').mkdir()
            Image.new('RGB', (64, 64), 'gray').save(root / 'real/base.jpg')
            with patch('scripts.training.synthesize_training_variants.parse_args', return_value=SimpleNamespace(
                    dataset_dir=str(root), source_class='real', limit=1, seed=7)):
                main()
            before = {p: p.read_bytes() for p in root.rglob('*.jpg')}
            state = random.getstate()
            self.assertEqual(audit(root, root / 'audit.json', limit=1), {'exact_match': 3})
            self.assertEqual(random.getstate(), state)
            self.assertTrue(all(p.read_bytes() == data for p, data in before.items()))
            target = root / 'alterada_manualmente/0001_base_manual.jpg'
            target.write_bytes(b'changed')
            self.assertEqual(audit(root, root / 'tampered.json', limit=1), {'mismatch': 1, 'exact_match': 2})
            with self.assertRaises(FileExistsError):
                audit(root, root / 'audit.json', limit=1)
