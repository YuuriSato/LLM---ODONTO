"""Train/validate/test a CNN with independent source groups and immutable runs."""
import argparse
import json
from pathlib import Path
import random
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import numpy as np
import torch
from torch import nn
from torch.utils.data import DataLoader, Dataset

from app.neural.dataset import read_manifest, digest
from app.neural.model import ARCHITECTURE, IMAGE_SIZE, DentalCNN, image_tensor


class ImageDataset(Dataset):
    def __init__(self, manifest, root, split):
        self.rows = [row for row in manifest['samples'] if row['split'] == split]
        self.classes, self.root = manifest['classes'], root

    def __len__(self):
        return len(self.rows)

    def __getitem__(self, index):
        row = self.rows[index]
        return image_tensor(self.root / row['file']), self.classes.index(row['label'])


def evaluate(model, loader, device, classes):
    matrix = np.zeros((len(classes), len(classes)), dtype=int)
    loss, total = 0.0, 0
    criterion = nn.CrossEntropyLoss(reduction='sum')
    model.eval()
    with torch.inference_mode():
        for images, labels in loader:
            logits = model(images.to(device))
            loss += criterion(logits, labels.to(device)).item()
            predictions = logits.argmax(dim=1).cpu().tolist()
            for expected, predicted in zip(labels.tolist(), predictions):
                matrix[expected, predicted] += 1
            total += len(labels)
    recalls = [float(matrix[i, i] / matrix[i].sum()) for i in range(len(classes))]
    return {'samples': total, 'loss': loss / total, 'accuracy': float(matrix.trace() / total),
            'balanced_accuracy': sum(recalls) / len(recalls), 'classes': classes,
            'confusion_matrix_rows_expected': matrix.tolist(), 'recall_by_class': dict(zip(classes, recalls)),
            'confidence_is_calibrated': False}


def train(manifest_path, output, *, epochs=10, batch_size=16, seed=17, device='cpu'):
    if epochs < 1 or batch_size < 1:
        raise ValueError('Epochs e batch-size devem ser positivos.')
    manifest = read_manifest(manifest_path)
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.set_num_threads(max(1, min(torch.get_num_threads(), 4)))
    torch.use_deterministic_algorithms(True)
    if device == 'cuda' and not torch.cuda.is_available():
        raise ValueError('CUDA indisponivel; use --device cpu.')
    output.mkdir(parents=True, exist_ok=False)
    config = {'architecture': ARCHITECTURE, 'image_size': IMAGE_SIZE, 'scope': manifest['scope'],
              'classes': manifest['classes'], 'epochs': epochs, 'batch_size': batch_size, 'seed': seed,
              'device': device, 'manifest_sha256': digest(manifest_path), 'torch_version': str(torch.__version__),
              'preprocessing': 'EXIF, RGB, aspect-preserving pad 192, bilinear, pixels /255',
              'selection': 'minimum validation cross-entropy; test evaluated only after selection'}
    (output / 'config.json').write_text(json.dumps(config, indent=2), encoding='utf-8')
    (output / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    datasets = {split: ImageDataset(manifest, manifest_path.parent, split) for split in ('train', 'validation', 'test')}
    loaders = {split: DataLoader(data, batch_size=batch_size, shuffle=split == 'train', num_workers=0)
               for split, data in datasets.items()}
    model = DentalCNN(len(manifest['classes'])).to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=0.001, weight_decay=0.01)
    counts = np.bincount([manifest['classes'].index(row['label']) for row in datasets['train'].rows], minlength=len(manifest['classes']))
    criterion = nn.CrossEntropyLoss(weight=torch.tensor(len(datasets['train']) / (len(counts) * counts), dtype=torch.float32, device=device))
    best_loss, best_state, history = float('inf'), None, []
    for epoch in range(1, epochs + 1):
        model.train()
        total_loss = 0.0
        for images, labels in loaders['train']:
            optimizer.zero_grad(set_to_none=True)
            loss = criterion(model(images.to(device)), labels.to(device))
            if not torch.isfinite(loss):
                raise ValueError('Loss nao finita; execucao interrompida sem aprovar checkpoint.')
            loss.backward()
            optimizer.step()
            total_loss += loss.item() * len(labels)
        validation = evaluate(model, loaders['validation'], device, manifest['classes'])
        if validation['loss'] < best_loss:
            best_loss = validation['loss']
            best_state = {key: value.detach().cpu().clone() for key, value in model.state_dict().items()}
            best_epoch = epoch
        history.append({'epoch': epoch, 'training_loss': total_loss / len(datasets['train']), 'validation': validation})
        (output / 'history.json').write_text(json.dumps(history, indent=2), encoding='utf-8')
        print(f'Epoch {epoch}/{epochs}: val_loss={validation["loss"]:.4f}, val_balanced_accuracy={validation["balanced_accuracy"]:.3f}', flush=True)
    model.load_state_dict(best_state)
    test = evaluate(model, loaders['test'], device, manifest['classes'])
    checkpoint = {**config, 'best_epoch': best_epoch, 'state_dict': best_state}
    torch.save(checkpoint, output / 'model.pt')
    report = {'scope': manifest['scope'], 'experimental': True, 'best_epoch': best_epoch,
              'checkpoint_sha256': digest(output / 'model.pt'), 'test': test,
              'clinical_or_forensic_validation': False,
              'limitations': ['O teste mede apenas este dataset. Nao estabelece generalizacao ou autenticidade.']}
    (output / 'evaluation.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('manifest', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--epochs', type=int, default=10)
    parser.add_argument('--batch-size', type=int, default=16)
    parser.add_argument('--seed', type=int, default=17)
    parser.add_argument('--device', choices=['cpu', 'cuda'], default='cpu')
    args = parser.parse_args()
    print(json.dumps(train(args.manifest, args.output, epochs=args.epochs, batch_size=args.batch_size,
                           seed=args.seed, device=args.device), ensure_ascii=False, indent=2))
