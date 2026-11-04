import csv
import json
from pathlib import Path
import tempfile
import unittest

from scripts.training.review_queue import build_queue


class ReviewQueueTests(unittest.TestCase):
    def test_duplicate_bridges_groups_without_approving_conflicting_labels(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            review = root / 'review.csv'
            rows = [
                ['a', 'same', 'REAL', 'one', ''],
                ['b', 'same', 'EDICAO_TRADICIONAL', 'two', ''],
                ['variant', 'different', 'SEM_ROTULO', 'two', ''],
            ]
            with review.open('w', newline='', encoding='utf-8-sig') as stream:
                writer = csv.writer(stream)
                writer.writerow(['file', 'sha256', 'candidate_label', 'group_candidate', 'read_error'])
                writer.writerows(rows)
            before = review.read_bytes()
            summary = build_queue(review, root / 'queue')
            self.assertEqual(summary['unique_contents'], 2)
            self.assertEqual(summary['conflicting_labels'], 1)
            self.assertEqual(summary['candidate_components'], 1)
            entries = json.loads((root / 'queue/queue.json').read_text(encoding='utf-8'))['entries']
            self.assertTrue(all(not entry['verified'] for entry in entries))
            self.assertEqual(review.read_bytes(), before)
            with self.assertRaises(FileExistsError):
                build_queue(review, root / 'queue')
