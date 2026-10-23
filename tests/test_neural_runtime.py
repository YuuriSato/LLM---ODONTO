import importlib.util
from pathlib import Path
import tempfile
import unittest


@unittest.skipUnless(importlib.util.find_spec('torch'), 'Executar no ambiente .venv-neural')
class NeuralRuntimeTests(unittest.TestCase):
    def test_checkpoint_roundtrip_preserves_predictions(self):
        import torch
        from PIL import Image
        from app.neural.model import DentalCNN, ARCHITECTURE, IMAGE_SIZE, image_tensor, predict
        torch.manual_seed(17)
        model = DentalCNN(2).eval()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            image = root / 'image.png'
            Image.new('RGB', (320, 100), 'red').save(image)
            checkpoint = root / 'model.pt'
            torch.save({'architecture': ARCHITECTURE, 'image_size': IMAGE_SIZE, 'scope': 'engineering',
                        'classes': ['A', 'B'], 'state_dict': model.state_dict()}, checkpoint)
            with torch.inference_mode():
                expected = model(image_tensor(image).unsqueeze(0)).softmax(dim=1)[0].tolist()
            result = predict(image, checkpoint)
            self.assertAlmostEqual(result['class_scores']['A'], expected[0], places=6)
            self.assertAlmostEqual(result['class_scores']['B'], expected[1], places=6)
            self.assertEqual(result['scope'], 'engineering')

    def test_incompatible_preprocessing_is_rejected(self):
        import torch
        from app.neural.model import load_checkpoint, ARCHITECTURE
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'bad.pt'
            torch.save({'architecture': ARCHITECTURE, 'image_size': 64}, path)
            with self.assertRaisesRegex(ValueError, 'incompatível'):
                load_checkpoint(path)
