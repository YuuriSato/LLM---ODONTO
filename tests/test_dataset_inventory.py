import csv
from pathlib import Path
import shutil
import tempfile
import unittest
from PIL import Image
from scripts.training.inventory_dataset import inventory
from scripts.training.build_reviewed_manifest import build
from app.neural.dataset import DENTAL_CLASSES, SPLITS, read_manifest


class InventoryTests(unittest.TestCase):
    def test_reviewed_samples_build_a_portable_verified_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'data'
            source.mkdir()
            for index in range(len(DENTAL_CLASSES) * len(SPLITS)):
                Image.new('RGB', (32, 32), (index * 20, 12, 55)).save(source / f'{index:02}.png')
            inventory(source, root / 'review')
            review = root / 'review/review.csv'
            with review.open(encoding='utf-8-sig', newline='') as stream:
                reader = csv.DictReader(stream)
                fields = reader.fieldnames
                rows = list(reader)
            for index, row in enumerate(rows):
                row.update(include='yes', verified_label=DENTAL_CLASSES[index % len(DENTAL_CLASSES)],
                           split=sorted(SPLITS)[index // len(DENTAL_CLASSES)], verified_group=f'group-{index}',
                           provenance='Synthetic test fixture only', reviewer='unit-test', reviewed_at='2026-10-22')
            with review.open('w', encoding='utf-8-sig', newline='') as stream:
                writer = csv.DictWriter(stream, fieldnames=fields)
                writer.writeheader()
                writer.writerows(rows)
            manifest = build(review, source, root / 'approved')
            self.assertTrue(manifest.is_file())
            read_manifest(manifest)
            self.assertEqual(len(list((root / 'approved/images').iterdir())), 12)

    def test_inventory_groups_variants_and_finds_duplicates_without_assigning_truth(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for folder in ('real', 'alterada_manualmente', 'copies'):
                (root / 'data' / folder).mkdir(parents=True)
            original = root / 'data/real/sample.jpg'
            Image.new('RGB', (32, 32), 'white').save(original)
            shutil.copyfile(original, root / 'data/copies/sample.jpg')
            Image.new('RGB', (32, 32), 'red').save(root / 'data/alterada_manualmente/0001_sample_manual.jpg')
            summary = inventory(root / 'data', root / 'review')
            self.assertEqual(summary['duplicate_copies'], 1)
            self.assertEqual(summary['candidate_groups'], 1)
            with (root / 'review/review.csv').open(encoding='utf-8-sig') as stream:
                rows = list(csv.DictReader(stream))
            self.assertTrue(all(row['verified_label'] == '' and row['include'] == 'no' for row in rows))
            with self.assertRaisesRegex(ValueError, 'Nenhuma amostra'):
                build(root / 'review/review.csv', root / 'data', root / 'approved')
            self.assertFalse((root / 'approved').exists())

    def test_inventory_never_overwrites_previous_review(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'data').mkdir()
            Image.new('RGB', (32, 32)).save(root / 'data/image.png')
            inventory(root / 'data', root / 'review')
            with self.assertRaises(FileExistsError):
                inventory(root / 'data', root / 'review')
