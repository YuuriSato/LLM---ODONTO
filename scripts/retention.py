"""Preview retention by default; application requires exclusive ownership of runtime."""
import argparse
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import re
import sqlite3
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.file_lock import ResourceBusy, file_lock
from app.history_store import HistoryStore


def expired_at(value, cutoff):
    try:
        # Legacy timestamps are local; new timestamps carry their UTC offset.
        return datetime.fromisoformat(value).astimezone(timezone.utc) < cutoff
    except (TypeError, ValueError):
        return False


def safe_path(path: Path, root: Path) -> bool:
    try:
        relative = path.relative_to(root)
        current = root
        for part in relative.parts:
            current /= part
            if current.is_symlink() or current.is_junction():
                return False
        return path.resolve().is_relative_to(root)
    except (ValueError, OSError):
        return False


def runtime_root(runtime: Path) -> Path:
    root = runtime.absolute()
    if any(path.is_symlink() or path.is_junction() for path in (root, *root.parents)):
        raise ValueError('Runtime nao pode ser um link ou junction.')
    for name in ('analysis_history.sqlite3', 'analysis_history.json', 'jobs.sqlite3',
                 'integrity_calibration.json', 'uploads', 'analysis_cache', '.service.lock', '.dataset.lock'):
        if not safe_path(root / name, root):
            raise ValueError('Caminho privado redirecionado; retencao interrompida.')
    return root


def retention_plan(runtime: Path, days: int) -> dict:
    if days < 1:
        raise ValueError('Retencao deve ser de pelo menos um dia.')
    root = runtime_root(runtime)
    store = HistoryStore(root / 'analysis_history.sqlite3', root / 'analysis_history.json')
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    with store.connection() as db:
        records = [(identifier, json.loads(payload)) for identifier, payload in db.execute('SELECT id, payload FROM history')]
    candidates = [(identifier, entry) for identifier, entry in records if expired_at(entry.get('created_at'), cutoff)]
    keep = [entry for _, entry in records if not expired_at(entry.get('created_at'), cutoff)]
    calibration_path = root / 'integrity_calibration.json'
    if calibration_path.exists():
        calibration = json.loads(calibration_path.read_text(encoding='utf-8-sig'))
        if not isinstance(calibration, dict):
            raise ValueError('Calibracao invalida; retencao interrompida.')
        keep.extend(entry for entry in calibration.values() if isinstance(entry, dict))
    protected_files = {entry.get(key) for entry in keep for key in ('stored_filename', 'original_stored_filename')}
    protected_analyses = {entry.get('analysis_id') for entry in keep}
    files = set()
    for _, entry in candidates:
        for key in ('stored_filename', 'original_stored_filename'):
            name = entry.get(key)
            if isinstance(name, str) and name not in protected_files and re.fullmatch(r'[a-f0-9]{32}\.(png|jpe?g|webp|bmp)', name):
                files.add(root / 'uploads' / name)
        identifier = entry.get('analysis_id')
        if isinstance(identifier, str) and identifier not in protected_analyses and re.fullmatch(r'[a-f0-9]{32}', identifier):
            folder = root / 'analysis_cache' / identifier
            if safe_path(folder, root) and folder.is_dir():
                files.update(folder.glob('*.json'))
    safe_files = [str(path) for path in files if safe_path(path, root) and path.is_file()]

    # Remove the legacy copy only if every entry is still represented exactly in SQLite.
    legacy = root / 'analysis_history.json'
    legacy_matches = True
    if legacy.exists():
        entries = json.loads(legacy.read_text(encoding='utf-8-sig'))
        encoded = {json.dumps(entry, sort_keys=True) for _, entry in records}
        legacy_matches = isinstance(entries, list) and all(json.dumps(entry, sort_keys=True) in encoded for entry in entries)
    return {'ids': [identifier for identifier, _ in candidates], 'files': sorted(safe_files),
            'days': days, 'cutoff': cutoff.isoformat(), 'legacy_matches': legacy_matches,
            'remove_legacy': legacy.exists() and legacy_matches and bool(candidates), 'store': store}


def apply_retention(runtime: Path, days: int) -> dict:
    root = runtime_root(runtime)
    with file_lock(root / '.service.lock'), file_lock(root / '.dataset.lock'):
        # Rebuild under the lock; a preview is never accepted as a deletion instruction.
        plan = retention_plan(root, days)
        if not plan['legacy_matches']:
            raise ValueError('Historico legado mudou desde a migracao. Resolva a divergencia antes de aplicar retencao.')
        store = plan.pop('store')
        for filename in plan['files']:
            path = Path(filename)
            if not safe_path(path, root):
                raise ValueError('Caminho de retencao mudou; operacao interrompida.')
            path.unlink(missing_ok=True)
        with store.connection() as db:
            db.executemany('DELETE FROM history WHERE id=?', [(identifier,) for identifier in plan['ids']])
        if plan['remove_legacy']:
            (root / 'analysis_history.json').unlink()
        jobs = root / 'jobs.sqlite3'
        if jobs.exists():
            db = sqlite3.connect(jobs)
            try:
                with db:
                    rows = db.execute("SELECT id, updated_at FROM jobs WHERE state NOT IN ('aguardando','executando','cancelando')").fetchall()
                    cutoff = datetime.fromisoformat(plan['cutoff'])
                    db.executemany('DELETE FROM jobs WHERE id=?', [(identifier,) for identifier, updated in rows if expired_at(updated, cutoff)])
            finally:
                db.close()
        return plan


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--days', type=int, default=90)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1] / 'runtime'
    try:
        plan = apply_retention(root, args.days) if args.apply else retention_plan(root, args.days)
    except (ResourceBusy, ValueError) as exc:
        parser.exit(1, str(exc) + '\n')
    plan.pop('store', None)
    print(json.dumps(plan, indent=2))


if __name__ == '__main__':
    main()
