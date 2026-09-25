import unittest
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
from app.evaluation import digest, held_out_hashes, load_manifest, summarize
from app.file_lock import ResourceBusy, file_lock
from scripts.register_sample import register_sample


class EvaluationTests(unittest.TestCase):
    def test_abstentions_failures_and_unverified_not_reported_as_correct(self):
        pairs = [('REAL', 'IA_EDITADA', 'concluida', True),
                 ('IA_EDITADA', 'REAL', 'concluida', True),
                 ('REAL', 'INDETERMINADO', 'concluida', True),
                 ('REAL', None, 'nao_concluida', True),
                 ('REAL', 'REAL', 'concluida', False)]
        rows = [dict(model='test', quality='boa', expected=a, predicted=b, status=c, verified=d) for a, b, c, d in pairs]
        result = summarize(rows)['groups'][0]
        self.assertEqual(result['eligible'], 4)
        self.assertEqual(result['coverage'], .5)
        self.assertEqual(result['accuracy_on_decided'], 0)
        self.assertEqual(result['indeterminate'], 1)
        self.assertEqual(result['technical_failures'], 1)
        self.assertEqual(result['false_positives'], 1)
        self.assertEqual(result['false_negatives'], 1)

    def test_empty_population_does_not_fabricate_rates(self):
        result = summarize([dict(model='test', expected=None, predicted=None, status='nao_concluida', verified=False)])['groups'][0]
        self.assertIsNone(result['accuracy_on_decided'])
        self.assertIsNone(result['false_positive_rate_completed_real'])

    def test_failed_response_cannot_keep_a_stale_verdict_in_confusion(self):
        row = dict(model='test', expected='REAL', predicted='REAL', status='nao_concluida', verified=True)
        result = summarize([row])['groups'][0]
        self.assertEqual(result['confusion'][0]['predicted'], 'NAO_CONCLUIDA')
        self.assertIsNone(result['accuracy_on_decided'])


class ManifestTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name) / 'datasets'
        self.root.mkdir()
        self.path = self.root / 'manifest.json'
        for name in ('image', 'reference', 'other'):
            (self.root / name).write_bytes(name.encode())

    def sample(self, name='image', split='test', reference=None):
        return dict(id=name, file=name, sha256=digest(self.root / name), group=name, split=split,
                    ground_truth='IA_EDITADA', provenance='Synthetic test fixture', verified=True,
                    scope='engineering', reference=reference,
                    reference_sha256=digest(self.root / reference) if reference else None)

    def write_manifest(self, samples):
        self.path.write_text(json.dumps(dict(schema_version='1.0', samples=samples)), encoding='utf-8')

    def test_reference_hash_checked_and_included_in_held_out(self):
        self.write_manifest([self.sample(reference='reference')])
        self.assertEqual(held_out_hashes(self.path), {digest(self.root / 'image'), digest(self.root / 'reference')})
        (self.root / 'reference').write_bytes(b'tampered')
        with self.assertRaisesRegex(ValueError, 'referencia'):
            load_manifest(self.path)

    def test_missing_reference_hash_and_orphan_hash_rejected(self):
        for sample in (self.sample(reference='reference'), self.sample()):
            sample['reference_sha256'] = None if sample['reference'] else '0' * 64
            self.write_manifest([sample])
            with self.assertRaises(ValueError):
                load_manifest(self.path)

    def test_duplicates_and_group_leakage(self):
        original = self.sample()
        duplicate = {**original, 'id': 'duplicate'}
        other = {**self.sample('other', 'calibration'), 'group': original['group']}
        for samples in ([original, duplicate], [original, other]):
            self.write_manifest(samples)
            with self.assertRaises(ValueError):
                load_manifest(self.path)

    def test_reference_cross_split_in_both_orders(self):
        samples = [self.sample(reference='reference'), self.sample('reference', 'calibration')]
        for order in (samples, list(reversed(samples))):
            self.write_manifest(order)
            with self.assertRaises(ValueError):
                load_manifest(self.path)

    def test_external_paths_rejected(self):
        outside = self.root.parent / 'outside'
        outside.write_bytes(b'private')
        sample = {**self.sample(), 'file': '../outside', 'sha256': digest(outside)}
        self.write_manifest([sample])
        with self.assertRaises(ValueError):
            load_manifest(self.path)

    def test_register_is_locked_and_failed_registration_keeps_manifest(self):
        args = SimpleNamespace(image=self.root / 'image', reference=self.root / 'reference', group='pair',
                               split='test', label='IA_EDITADA', provenance='Synthetic', verified=True,
                               scope='engineering', transformation='Test')
        with file_lock(self.root.parent / '.dataset.lock'), self.assertRaises(ResourceBusy):
            register_sample(args, self.root)
        register_sample(args, self.root)
        before = self.path.read_bytes()
        files = set(self.root.iterdir())
        with self.assertRaises(ValueError):
            register_sample(args, self.root)
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(set(self.root.iterdir()), files)

    def test_calibration_image_cannot_be_registered_as_test(self):
        (self.root.parent / 'integrity_calibration.json').write_text(json.dumps({digest(self.root / 'reference'): {}}))
        args = SimpleNamespace(image=self.root / 'image', reference=self.root / 'reference', group='pair',
                               split='test', label='IA_EDITADA', provenance='Synthetic', verified=True,
                               scope='engineering', transformation=None)
        with self.assertRaisesRegex(ValueError, 'calibracao'):
            register_sample(args, self.root)
        self.assertFalse(self.path.exists())
