import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from app.ai.config import AISettings
from app.evaluation import DatasetManifest, digest
from scripts.evaluate_integrity import evaluate_samples, select_samples


class EvaluationRunnerTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        samples = []
        for identifier, split, label, verified in (
            ('first', 'test', 'IA_EDITADA', True), ('unknown', 'test', None, False),
            ('second', 'test', 'REAL', True), ('training', 'calibration', 'IA_GERADA', True),
        ):
            path = self.root / (identifier + '.png')
            path.write_bytes(identifier.encode())
            samples.append(dict(id=identifier, file=path.name, sha256=digest(path), group=identifier,
                                split=split, ground_truth=label, verified=verified,
                                scope='engineering', provenance='Test fixture'))
        self.manifest = DatasetManifest.model_validate_json(json.dumps({'schema_version': '1.0', 'samples': samples}))
        self.settings = AISettings(provider='lmstudio', model='fixture', development=True, timeout_seconds=360)

    def result(self, failed=False):
        return dict(status='nao_concluida' if failed else 'concluida',
                    verdict=None if failed else 'INDETERMINADO', forensic_quality='boa',
                    analysis_id='fixture', error_code='timeout' if failed else None, duration_seconds='1.2')

    def test_selection_excludes_calibration_and_obeys_verification_ids_and_limit(self):
        selected = select_samples(self.manifest, verified_only=True)
        self.assertEqual([sample.id for sample in selected], ['first', 'second'])
        self.assertEqual(select_samples(self.manifest, verified_only=True, limit=1), selected[:1])
        self.assertEqual([sample.id for sample in select_samples(self.manifest, sample_ids=['second'])], ['second'])
        self.assertEqual(select_samples(self.manifest, sample_ids=['unknown'], verified_only=True), [])
        for identifier in ('training', 'missing'):
            with self.assertRaises(ValueError):
                select_samples(self.manifest, sample_ids=[identifier])
        with self.assertRaises(ValueError):
            select_samples(self.manifest, limit=0)

    def test_stops_on_technical_failure_and_preserves_selection_and_partial_report(self):
        samples = select_samples(self.manifest, verified_only=True)
        output = self.root / 'run'
        with patch('scripts.evaluate_integrity.run_integrity_pipeline', return_value=self.result(True)) as pipeline:
            rows = evaluate_samples(samples, self.root / 'manifest.json', self.settings, output)
        pipeline.assert_called_once()
        self.assertEqual(pipeline.call_args.kwargs['calibration'], {})
        self.assertEqual(pipeline.call_args.args, (self.root / 'first.png', None))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['error_code'], 'timeout')
        report = json.loads((output / 'report.json').read_text())
        self.assertEqual(report['execution'], {'planned': 2, 'attempted': 1, 'remaining': 1, 'stopped_on_error': True})
        self.assertEqual(report['engineering']['groups'][0]['technical_failures'], 1)
        self.assertIsNone(report['engineering']['groups'][0]['accuracy_on_decided'])
        selection = json.loads((output / 'selection.json').read_text())
        self.assertEqual(selection['timeout_seconds'], 360)
        self.assertEqual([sample['id'] for sample in selection['samples']], ['first', 'second'])

    def test_explicit_continue_records_failure_and_abstention_without_accuracy(self):
        output = self.root / 'run'
        samples = select_samples(self.manifest, verified_only=True)
        with patch('scripts.evaluate_integrity.run_integrity_pipeline', side_effect=[self.result(True), self.result()]):
            rows = evaluate_samples(samples, self.root / 'manifest.json', self.settings, output, continue_on_error=True)
        self.assertEqual(len(rows), 2)
        report = json.loads((output / 'report.json').read_text())
        self.assertEqual(report['execution']['remaining'], 0)
        self.assertFalse(report['execution']['stopped_on_error'])
        metrics = report['engineering']['groups'][0]
        self.assertEqual(metrics['technical_failures'], 1)
        self.assertEqual(metrics['indeterminate'], 1)
        self.assertEqual(metrics['coverage'], 0)
        self.assertIsNone(metrics['accuracy_on_decided'])
        before = (output / 'report.json').read_bytes()
        with self.assertRaises(FileExistsError):
            evaluate_samples(samples, self.root / 'manifest.json', self.settings, output)
        self.assertEqual((output / 'report.json').read_bytes(), before)


if __name__ == '__main__':
    unittest.main()
