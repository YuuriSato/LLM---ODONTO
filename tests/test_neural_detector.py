import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, Mock
from app.ai.neural_detector import NeuralDetector, configured_neural_detector


class NeuralDetectorTests(unittest.TestCase):
    def test_production_does_not_activate_optional_network(self):
        with patch.dict('os.environ', {'NEURAL_CHECKPOINT': 'test.pt'}):
            self.assertIsNone(configured_neural_detector(False))
            self.assertIsNotNone(configured_neural_detector(True))

    def test_engineering_model_cannot_supply_dental_evidence(self):
        response = Mock(stdout=json.dumps({'scope': 'engineering', 'class_scores': {'A': 0.5, 'B': 0.5}}))
        with patch('app.ai.neural_detector.subprocess.run', return_value=response):
            with self.assertRaisesRegex(ValueError, 'engenharia'):
                NeuralDetector(Path('test.pt')).analyze(Path('image.png'))

    def test_uncalibrated_neural_scores_do_not_assert_ai(self):
        response = Mock(stdout=json.dumps({'scope': 'dental', 'class_scores': {
            'REAL': 0.01, 'EDICAO_TRADICIONAL': 0.01, 'IA_GERADA': 0.97, 'IA_EDITADA': 0.01}}))
        with tempfile.TemporaryDirectory() as directory, patch('app.ai.neural_detector.subprocess.run', return_value=response):
            checkpoint = Path(directory) / 'test.pt'
            checkpoint.write_bytes(b'test fixture')
            result = NeuralDetector(checkpoint).analyze(Path('image.png'))
        self.assertEqual(result.conclusion, 'inconclusivo')
        self.assertAlmostEqual(result.score, 0.98)
        self.assertIn('nao_calibrado', result.scale)
