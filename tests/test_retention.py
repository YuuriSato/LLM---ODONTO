from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest

from app.file_lock import ResourceBusy, file_lock
from app.history_store import HistoryStore
from scripts.retention import apply_retention, expired_at, retention_plan, safe_path


class RetentionTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.legacy = self.root / 'analysis_history.json'
        self.store = HistoryStore(self.root / 'analysis_history.sqlite3')
        self.old = (datetime.now(timezone.utc) - timedelta(days=100)).isoformat()
        self.now = datetime.now(timezone.utc).isoformat()

    def upload(self, letter):
        path = self.root / 'uploads' / (letter * 32 + '.png')
        path.parent.mkdir(exist_ok=True)
        path.write_bytes(b'fixture')
        return path

    def test_preview_preserves_data_and_apply_removes_only_expired(self):
        old, recent = self.upload('a'), self.upload('b')
        self.store.append(dict(id='old', created_at=self.old, stored_filename=old.name))
        self.store.append(dict(id='new', created_at=self.now, stored_filename=recent.name))
        plan = retention_plan(self.root, 90)
        self.assertEqual(plan['ids'], ['old'])
        self.assertTrue(old.exists())
        self.assertEqual(len(self.store.all()), 2)
        apply_retention(self.root, 90)
        self.assertFalse(old.exists())
        self.assertTrue(recent.exists())
        self.assertEqual([e['id'] for e in self.store.all()], ['new'])

    def test_shared_uploads_cache_and_calibration_protected(self):
        shared, calibrated = self.upload('a'), self.upload('b')
        folder = self.root / 'analysis_cache' / ('c' * 32)
        folder.mkdir(parents=True)
        evidence = folder / 'local_evidence.json'
        evidence.write_text('{}')
        self.store.append(dict(id='old', created_at=self.old, stored_filename=shared.name,
                               original_stored_filename=calibrated.name, analysis_id=folder.name))
        self.store.append(dict(id='recent', created_at=self.now, stored_filename=shared.name, analysis_id=folder.name))
        (self.root / 'integrity_calibration.json').write_text(json.dumps({'hash': {'stored_filename': calibrated.name}}))
        self.assertEqual(retention_plan(self.root, 90)['files'], [])
        apply_retention(self.root, 90)
        self.assertTrue(all(path.exists() for path in (shared, calibrated, evidence)))

    def test_legacy_without_id_deleted_using_database_key(self):
        self.legacy.write_text(json.dumps([dict(created_at=self.old)]))
        apply_retention(self.root, 90)
        self.assertEqual(self.store.all(), [])
        self.assertFalse(self.legacy.exists())

    def test_changed_legacy_refuses_apply_before_deleting_files(self):
        image = self.upload('a')
        self.legacy.write_text(json.dumps([dict(id='old', created_at=self.old, stored_filename=image.name)]))
        retention_plan(self.root, 90)
        self.legacy.write_text(json.dumps([dict(id='unmigrated', created_at=self.now)]))
        with self.assertRaisesRegex(ValueError, 'legado mudou'):
            apply_retention(self.root, 90)
        self.assertTrue(image.exists())
        self.assertEqual(len(self.store.all()), 1)

    def test_service_lock_prevents_retention_in_another_process(self):
        with file_lock(self.root / '.service.lock'):
            command = 'from pathlib import Path; from scripts.retention import apply_retention; apply_retention(Path(__import__("sys").argv[1]), 90)'
            child = subprocess.run([sys.executable, '-c', command, str(self.root)], capture_output=True, text=True, timeout=10)
            self.assertNotEqual(child.returncode, 0)
            self.assertIn('ResourceBusy', child.stderr)
        # Releasing the OS handle makes the next operation possible.
        apply_retention(self.root, 90)

    def test_dataset_lock_prevents_apply(self):
        with file_lock(self.root / '.dataset.lock'), self.assertRaises(ResourceBusy):
            apply_retention(self.root, 90)

    def test_unsafe_names_never_target_files_outside_runtime(self):
        self.store.append(dict(id='old', created_at=self.old, stored_filename='../private.png', analysis_id='../'))
        self.assertEqual(retention_plan(self.root, 90)['files'], [])
        self.assertFalse(safe_path(self.root.parent / 'private.png', self.root))

    def test_symlink_parent_not_followed(self):
        destination = self.root / 'kept'
        destination.mkdir()
        link = self.root / 'uploads'
        try:
            link.symlink_to(destination, target_is_directory=True)
        except OSError:
            self.skipTest('Symlinks need Windows developer mode or privileges')
        with self.assertRaises(ValueError):
            retention_plan(self.root, 90)

    def test_jobs_active_unknown_dates_and_recent_entries_kept(self):
        path = self.root / 'jobs.sqlite3'
        db = sqlite3.connect(path)
        try:
            with db:
                db.execute('CREATE TABLE jobs (id TEXT, state TEXT, updated_at TEXT)')
                db.executemany('INSERT INTO jobs VALUES (?, ?, ?)', [('old', 'concluida', self.old), ('active', 'executando', self.old), ('invalid', 'falhou', ''), ('new', 'falhou', self.now)])
            apply_retention(self.root, 90)
            self.assertEqual({row[0] for row in db.execute('SELECT id FROM jobs')}, {'active', 'invalid', 'new'})
        finally:
            db.close()

    def test_expiration_honors_timezone_and_invalid_dates(self):
        cutoff = datetime(2026, 1, 1, 12, tzinfo=timezone.utc)
        self.assertFalse(expired_at('2026-01-01T10:00:00-03:00', cutoff))
        self.assertTrue(expired_at('2026-01-01T14:00:00+03:00', cutoff))
        self.assertFalse(expired_at(None, cutoff))
        self.assertFalse(expired_at('unknown', cutoff))
