from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
import json
from pathlib import Path
import tempfile
from threading import Event
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from PIL import Image

from app.history_store import HistoryStore
from app.jobs import JobQueue, QueueFull
from app.uploads import save_image


class StorageUploadJobTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def test_migration_is_once_lossless_and_over_100(self):
        legacy = self.root / 'old.json'
        entries = [{'id': str(i), 'created_at': str(i).zfill(4), 'verdict': 'MODIFICADO'} for i in range(150)]
        legacy.write_text(json.dumps(entries), encoding='utf-8')
        store = HistoryStore(self.root / 'history.sqlite3', legacy)
        self.assertEqual(len(store.all()), 150)
        self.assertEqual(json.loads(legacy.read_text()), entries)
        self.assertEqual(len(HistoryStore(store.path, legacy).all()), 150)
        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(store.append, [{'id': f'new{i}'} for i in range(20)]))
        self.assertEqual(len(store.all()), 170)

    def test_invalid_uploads_leave_no_files(self):
        for name, data in [('test.png', b'not an image'), ('test.svg', b'<svg/>')]:
            with self.assertRaises(ValueError):
                save_image(SimpleNamespace(filename=name, file=BytesIO(data)), self.root / 'uploads')
        self.assertFalse((self.root / 'uploads').exists())

    def test_size_pixels_and_format_limits(self):
        stream = BytesIO()
        Image.new('RGB', (32, 32), 'red').save(stream, format='PNG')
        data = stream.getvalue()
        def field(name='test.png'):
            return SimpleNamespace(filename=name, file=BytesIO(data))
        with patch('app.uploads.MAX_FILE_BYTES', 10), self.assertRaises(ValueError):
            save_image(field(), self.root)
        with patch('app.uploads.MAX_PIXELS', 10), self.assertRaises(ValueError):
            save_image(field(), self.root)
        with self.assertRaises(ValueError):
            save_image(field('test.jpg'), self.root)
        self.assertEqual(save_image(field(), self.root).read_bytes(), data)

    def test_bounded_queue_cancel_and_restart(self):
        queue = JobQueue(self.root / 'jobs.sqlite3', capacity=2)
        gate, started = Event(), Event()
        def operation(cancelled):
            started.set()
            gate.wait(5)
            return {'status': 'concluida'}
        first = queue.submit(operation)
        self.assertTrue(started.wait(2))
        second = queue.submit(lambda _: self.fail('Cancelled job must not execute'))
        with self.assertRaises(QueueFull):
            queue.submit(operation)
        self.assertEqual(queue.cancel(second)['state'], 'cancelada')
        self.assertEqual(queue.cancel(first)['state'], 'cancelando')
        gate.set()
        queue.pending.join()
        self.assertEqual(queue.get(first)['state'], 'cancelada')
        queue.close()
        with queue.connect() as db:
            db.execute("INSERT INTO jobs VALUES ('interrupted', 'executando', '', '{}')")
        reopened = JobQueue(queue.path)
        try:
            self.assertEqual(reopened.get('interrupted')['state'], 'falhou')
        finally:
            reopened.close()

    def test_cancel_cannot_overwrite_finished_job_before_active_cleanup(self):
        queue = JobQueue(self.root / 'jobs.sqlite3')
        self.addCleanup(queue.close)
        for state in ('concluida', 'falhou', 'cancelada'):
            event = Event()
            queue.active['race'] = event
            queue._save('race', state, {'result': {'status': 'concluida'}})
            self.assertEqual(queue.cancel('race')['state'], state)
            self.assertFalse(event.is_set())

    def test_failed_submit_does_not_consume_capacity(self):
        queue = JobQueue(self.root / 'jobs.sqlite3', capacity=1)
        self.addCleanup(queue.close)
        with patch.object(queue, '_save', side_effect=OSError('disk')), self.assertRaises(OSError):
            queue.submit(lambda _: {})
        self.assertEqual(queue.active, {})
        identifier = queue.submit(lambda _: {'status': 'concluida'})
        queue.pending.join()
        self.assertEqual(queue.get(identifier)['state'], 'concluida')

    def test_operation_failure_does_not_kill_worker_or_expose_exception(self):
        queue = JobQueue(self.root / 'jobs.sqlite3')
        self.addCleanup(queue.close)
        def broken(_):
            raise RuntimeError('secret-value')
        with self.assertLogs('app.jobs', level='ERROR') as logs:
            failed = queue.submit(broken)
            queue.pending.join()
        self.assertNotIn('secret-value', str(logs.output))
        self.assertNotIn('secret-value', str(queue.get(failed)))
        self.assertEqual(queue.get(failed)['state'], 'falhou')
        next_job = queue.submit(lambda _: {'status': 'concluida'})
        queue.pending.join()
        self.assertEqual(queue.get(next_job)['state'], 'concluida')
