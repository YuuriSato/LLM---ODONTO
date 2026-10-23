"""Compact CNN baseline with saved preprocessing, not a pretrained expert."""
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps
import torch
from torch import nn

ARCHITECTURE = 'dental-cnn-v1'
IMAGE_SIZE = 192


class DentalCNN(nn.Module):
    def __init__(self, classes: int):
        super().__init__()
        self.features = nn.Sequential(
            nn.Conv2d(3, 16, 3, padding=1), nn.ReLU(), nn.MaxPool2d(2),
            nn.Conv2d(16, 32, 3, padding=1), nn.ReLU(), nn.MaxPool2d(2),
            nn.Conv2d(32, 64, 3, padding=1), nn.ReLU(), nn.MaxPool2d(2),
            nn.AdaptiveAvgPool2d((4, 4)),
        )
        self.classifier = nn.Sequential(nn.Flatten(), nn.Linear(64 * 4 * 4, 128),
                                        nn.ReLU(), nn.Dropout(0.2), nn.Linear(128, classes))

    def forward(self, images):
        return self.classifier(self.features(images))


def image_tensor(path: Path):
    with Image.open(path) as source:
        image = ImageOps.exif_transpose(source).convert('RGB')
        image = ImageOps.pad(image, (IMAGE_SIZE, IMAGE_SIZE), method=Image.Resampling.BILINEAR, color=(127, 127, 127))
        pixels = np.array(image, dtype=np.float32) / 255.0
    return torch.from_numpy(pixels.transpose(2, 0, 1).copy())


def load_checkpoint(path: Path):
    checkpoint = torch.load(path, map_location='cpu', weights_only=True)
    if checkpoint.get('architecture') != ARCHITECTURE or checkpoint.get('image_size') != IMAGE_SIZE:
        raise ValueError('Arquitetura ou preprocessamento incompatível.')
    if checkpoint.get('scope') not in {'engineering', 'dental'}:
        raise ValueError('Checkpoint sem escopo.')
    classes = checkpoint['classes']
    if not isinstance(classes, list) or len(classes) < 2 or len(set(classes)) != len(classes):
        raise ValueError('Classes invalidas.')
    model = DentalCNN(len(classes))
    model.load_state_dict(checkpoint['state_dict'])
    model.eval()
    return model, checkpoint


def predict(path: Path, checkpoint_path: Path) -> dict:
    model, metadata = load_checkpoint(checkpoint_path)
    with torch.inference_mode():
        scores = torch.softmax(model(image_tensor(path).unsqueeze(0)), dim=1)[0].tolist()
    return {'scope': metadata['scope'], 'experimental': True,
            'class_scores': dict(zip(metadata['classes'], scores)),
            'predicted_class': metadata['classes'][int(np.argmax(scores))],
            'score_kind': 'softmax_nao_calibrado', 'architecture': ARCHITECTURE,
            'limitations': ['Baseline experimental; pontuacoes nao comprovam autenticidade nem validacao odontologica.']}
