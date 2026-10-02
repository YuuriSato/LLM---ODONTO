import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock
from zipfile import ZipInfo

from app.evaluation import digest, load_manifest
from scripts.download_hanoi import download
from scripts.import_alphadent import HTTPRangeReader, MAX_IMAGE_BYTES, merge_manifest, select_patients


class Response:
    def __init__(self, body, status=206, content_range=None):
        self.body = body
        self.status_code = status
        self.headers = {'Content-Range': content_range}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def raise_for_status(self):
        pass

    def iter_content(self, size):
        yield self.body


class ImportTransportTests(unittest.TestCase):
    def test_range_cache_seek_and_end(self):
        session = Mock()
        session.get.return_value = Response(b'abcdef', content_range='bytes 0-5/6')
        reader = HTTPRangeReader(session, 'https://source.test/archive', 6)
        self.assertEqual(reader.read(2), b'ab')
        reader.seek(-2, io.SEEK_END)
        self.assertEqual(reader.read(), b'ef')
        self.assertEqual(reader.read(1), b'')
        self.assertEqual(reader.transferred, 6)
        session.get.assert_called_once()
        with self.assertRaises(ValueError):
            reader.seek(7)

    def test_reject_ignored_range_wrong_extent_and_truncated_or_oversize_body(self):
        for response in (Response(b'abc', 200, 'bytes 0-2/3'),
                         Response(b'abc', content_range='bytes 1-3/4'),
                         Response(b'ab', content_range='bytes 0-2/3'),
                         Response(b'abcd', content_range='bytes 0-2/3')):
            session = Mock()
            session.get.return_value = response
            reader = HTTPRangeReader(session, 'https://source.test/archive', 3)
            with self.assertRaises(ValueError):
                reader.read(3)
            self.assertEqual(reader.tell(), 0)
            self.assertEqual(reader.transferred, 0)

    def test_request_budget_prevents_whole_archive_download(self):
        session = Mock()
        reader = HTTPRangeReader(session, 'https://source.test/archive', MAX_IMAGE_BYTES + 1)
        with self.assertRaises(ValueError):
            reader.read()
        session.get.assert_not_called()

    def test_resume_and_hash_verification(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'archive.rar'
            partial = target.with_suffix('.rar.part')
            partial.write_bytes(b'abc')
            session = Mock()
            session.get.return_value = Response(b'def', content_range='bytes 3-5/6')
            expected = hashlib.sha256(b'abcdef').hexdigest()
            download(session, 'https://source.test/archive', target, 6, expected)
            self.assertEqual(target.read_bytes(), b'abcdef')
            self.assertFalse(partial.exists())
            self.assertEqual(session.get.call_args.kwargs['headers']['Range'], 'bytes=3-')
            session.reset_mock()
            download(session, 'https://source.test/archive', target, 6, expected)
            session.get.assert_not_called()

    def test_resume_refusal_preserves_partial_and_hash_failure_never_promotes(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'archive.rar'
            partial = target.with_suffix('.rar.part')
            partial.write_bytes(b'abc')
            session = Mock()
            session.get.return_value = Response(b'abcdef', 200)
            with self.assertRaises(ValueError):
                download(session, 'https://source.test/archive', target, 6, '0' * 64)
            self.assertEqual(partial.read_bytes(), b'abc')
            session.get.return_value = Response(b'def', content_range='bytes 3-5/6')
            with self.assertRaises(ValueError):
                download(session, 'https://source.test/archive', target, 6, '0' * 64)
            self.assertFalse(target.exists())
            self.assertEqual(partial.read_bytes(), b'abcdef')


class DatasetImportTests(unittest.TestCase):
    def test_selection_is_repeatable_and_one_image_per_patient(self):
        infos = []
        for patient in range(5):
            for photo in range(3):
                item = ZipInfo(f'images/train/p{patient}_{photo}.jpg')
                item.file_size = item.compress_size = 100
                infos.append(item)
        selected = select_patients(infos, 4, 123)
        self.assertEqual(selected, select_patients(list(reversed(infos)), 4, 123))
        self.assertEqual(len({patient for patient, _ in selected}), 4)
        for unsafe in ('../images/p1_0.jpg', '/images/p1_0.jpg', 'images\\p1_0.jpg'):
            item = ZipInfo('placeholder')
            item.filename = unsafe
            with self.assertRaises(ValueError):
                select_patients([item], 1, 123)

    def test_merge_preserves_review_and_rejects_calibration_contamination_atomically(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / 'datasets'
            root.mkdir()
            (root / 'photo.jpg').write_bytes(b'fixture')
            sample = dict(id='photo', file='photo.jpg', sha256=digest(root / 'photo.jpg'),
                          group='patient1', split='test', ground_truth=None, verified=False,
                          scope='dental', provenance='Fixture source')
            merge_manifest([sample], root)
            saved = load_manifest(root / 'manifest.json')
            self.assertIsNone(saved.samples[0].ground_truth)
            self.assertFalse(saved.samples[0].verified)
            reviewed = saved.model_dump(mode='json')
            reviewed['samples'][0].update(ground_truth='IA_EDITADA', verified=True)
            (root / 'manifest.json').write_text(json.dumps(reviewed), encoding='utf-8')
            merge_manifest([sample], root)
            self.assertTrue(load_manifest(root / 'manifest.json').samples[0].verified)
            (root.parent / 'integrity_calibration.json').write_text(json.dumps({sample['sha256'].upper(): {}}))
            current = (root / 'manifest.json').read_bytes()
            with self.assertRaises(ValueError):
                merge_manifest([sample], root)
            self.assertEqual((root / 'manifest.json').read_bytes(), current)


if __name__ == '__main__':
    unittest.main()
