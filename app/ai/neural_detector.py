"""Optional neural evidence in development, isolated from the web Python runtime."""
import json
import os
from pathlib import Path
import subprocess

from app.ai.detector import DetectorResult
from app.neural.dataset import DENTAL_CLASSES, digest

ROOT = Path(__file__).resolve().parents[2]


class NeuralDetector:
    def __init__(self, checkpoint: Path, python: Path | None = None):
        self.checkpoint = checkpoint.resolve()
        self.python = python or ROOT / '.venv-neural' / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')

    def analyze(self, image: Path) -> DetectorResult:
        process = subprocess.run(
            [str(self.python), str(ROOT / 'scripts/training/predict_neural.py'), str(image.resolve()),
             '--checkpoint', str(self.checkpoint)], capture_output=True, text=True, encoding='utf-8',
            timeout=45, check=True,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
        )
        payload = json.loads(process.stdout)
        scores = payload['class_scores']
        if payload['scope'] != 'dental' or set(scores) != set(DENTAL_CLASSES):
            raise ValueError('Checkpoint de engenharia nao pode ser utilizado como detector odontologico.')
        if any(not isinstance(value, (float, int)) or not 0 <= value <= 1 for value in scores.values()):
            raise ValueError('Pontuacoes neurais invalidas.')
        if abs(sum(scores.values()) - 1) > 1e-5:
            raise ValueError('Distribuicao neural invalida.')
        return DetectorResult(
            provider='experimental_dental_cnn', version=digest(self.checkpoint), status='disponivel',
            score=scores['IA_GERADA'] + scores['IA_EDITADA'], scale='softmax_nao_calibrado_0_1',
            conclusion='inconclusivo',
            limitations=['Rede experimental sem validacao de campo; pontuacao nao decide o veredito.',
                         'Distribuicao de classes: ' + json.dumps(scores, ensure_ascii=True, sort_keys=True)],
        )


def configured_neural_detector(development: bool):
    path = os.environ.get('NEURAL_CHECKPOINT', '').strip()
    return NeuralDetector(Path(path)) if development and path else None
