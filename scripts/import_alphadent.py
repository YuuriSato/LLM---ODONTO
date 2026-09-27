"""Import a patient-separated pilot from the official AlphaDent archive using HTTP ranges."""
import argparse
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import random
import re
import sys
import uuid
import zipfile
import zlib

import requests
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.evaluation import digest, load_manifest
from app.file_lock import file_lock

REPOSITORY = 'ZFTurbo/AlphaDent'
REVISION = 'e927c42de11ba38bd1552d858c532b0c1031810e'
ARCHIVE_SHA256 = 'fd55fc05284821c1c2b338df3d9c691a2b7e95eedac0749ac7caad7d44c87821'
SIZE = 4877554182
URL = f'https://huggingface.co/datasets/{REPOSITORY}/resolve/{REVISION}/AlphaDent.zip'
DATASET_ROOT = Path(__file__).resolve().parents[1] / 'runtime' / 'datasets'
SOURCE_ROOT = DATASET_ROOT / 'sources' / 'alphadent-v1'
MAX_IMAGE_BYTES = 16 * 1024 * 1024


class HTTPRangeReader(io.RawIOBase):
    """Read-only bounded seekable transport; zipfile handles the archive format and CRC."""
    def __init__(self, session, url, size):
        self.session, self.url, self.size = session, url, size
        self.position = 0
        self.cache_start, self.cache = 0, b''
        self.transferred = 0

    def readable(self):
        return True

    def seekable(self):
        return True

    def tell(self):
        return self.position

    def seek(self, offset, whence=io.SEEK_SET):
        if whence not in (io.SEEK_SET, io.SEEK_CUR, io.SEEK_END):
            raise ValueError('Invalid seek mode')
        position = offset + (0 if whence == io.SEEK_SET else self.position if whence == io.SEEK_CUR else self.size)
        if not 0 <= position <= self.size:
            raise ValueError('Seek outside archive')
        self.position = position
        return position

    def read(self, size=-1):
        if size < 0:
            size = self.size - self.position
        size = min(size, self.size - self.position)
        if size == 0:
            return b''
        if size > MAX_IMAGE_BYTES:
            raise ValueError('Range exceeds the per-request byte budget')
        start, stop = self.position, self.position + size
        if not (self.cache_start <= start and stop <= self.cache_start + len(self.cache)):
            end = min(self.size, start + max(size, 65536)) - 1
            headers = {'Range': f'bytes={start}-{end}', 'Accept-Encoding': 'identity'}
            with self.session.get(self.url, headers=headers, stream=True, timeout=(20, 60)) as response:
                response.raise_for_status()
                expected = f'bytes {start}-{end}/{self.size}'
                if response.status_code != 206 or response.headers.get('Content-Range') != expected:
                    raise ValueError('Server did not honor the exact HTTP range')
                chunks, length = [], 0
                for chunk in response.iter_content(1024 * 1024):
                    length += len(chunk)
                    if length > end - start + 1:
                        raise ValueError('Range response larger than requested')
                    chunks.append(chunk)
                if length != end - start + 1:
                    raise ValueError('Truncated HTTP range')
                self.cache_start, self.cache = start, b''.join(chunks)
                self.transferred += length
        data = self.cache[start - self.cache_start:stop - self.cache_start]
        self.position = stop
        return data


def select_patients(infos, count, seed):
    patients = {}
    for info in infos:
        name = PurePosixPath(info.filename)
        if name.is_absolute() or '..' in name.parts or '\\' in info.filename or ':' in info.filename:
            raise ValueError('Unsafe archive member path')
        if info.is_dir() or name.suffix.lower() not in {'.jpg', '.jpeg', '.png'} or 'images' not in name.parts:
            continue
        patient = re.match(r'(p\d+)_', name.name, flags=re.I)
        if not patient:
            continue
        if not 0 < info.file_size <= MAX_IMAGE_BYTES or info.compress_size > MAX_IMAGE_BYTES:
            continue
        patients.setdefault(patient[1].lower(), []).append(info)
    rng = random.Random(seed)
    groups = sorted(patients)
    rng.shuffle(groups)
    return [(patient, rng.choice(sorted(patients[patient], key=lambda item: item.filename))) for patient in groups[:count]]


def merge_manifest(samples, root=DATASET_ROOT):
    with file_lock(root.parent / '.dataset.lock'):
        path = root / 'manifest.json'
        manifest = load_manifest(path).model_dump(mode='json') if path.exists() else {'schema_version': '1.0', 'samples': []}
        existing = {sample['id']: sample for sample in manifest['samples']}
        calibration = root.parent / 'integrity_calibration.json'
        calibrated = json.loads(calibration.read_text(encoding='utf-8-sig')) if calibration.exists() else {}
        for sample in samples:
            if sample['sha256'] in calibrated:
                raise ValueError('An imported image is already in calibration; review the split first.')
            if sample['id'] in existing:
                if existing[sample['id']]['sha256'] != sample['sha256']:
                    raise ValueError('Existing sample changed')
                continue
            manifest['samples'].append(sample)
        staging = root / (uuid.uuid4().hex + '.json')
        try:
            staging.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding='utf-8')
            load_manifest(staging)
            staging.replace(path)
        finally:
            staging.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--count', type=int, default=100)
    parser.add_argument('--seed', type=int, default=20260927)
    parser.add_argument('--list-only', action='store_true')
    args = parser.parse_args()
    if not 1 <= args.count <= 100:
        parser.error('Pilot count must be between 1 and 100.')
    SOURCE_ROOT.mkdir(parents=True, exist_ok=True)
    with file_lock(SOURCE_ROOT / '.import.lock'), requests.Session() as session:
        response = session.get(f'https://huggingface.co/api/datasets/{REPOSITORY}/revision/{REVISION}', timeout=30)
        response.raise_for_status()
        card = response.json()
        if card.get('cardData', {}).get('license') != 'apache-2.0':
            raise ValueError('License not confirmed on the pinned dataset revision')
        remote = HTTPRangeReader(session, URL, SIZE)
        with zipfile.ZipFile(remote) as archive:
            selected = select_patients(archive.infolist(), args.count, args.seed)
            print(f'Archive members: {len(archive.infolist())}; selected distinct patients: {len(selected)}', flush=True)
            if len(selected) < args.count:
                raise ValueError('Not enough patient-identified original images')
            if args.list_only:
                print(json.dumps([{'patient': patient, 'file': item.filename, 'bytes': item.file_size} for patient, item in selected[:5]], indent=2))
                return
            source = {
                'source': f'https://huggingface.co/datasets/{REPOSITORY}', 'revision': REVISION,
                'authors_repository': 'https://github.com/ZFTurbo/AlphaDent',
                'publication': 'https://arxiv.org/abs/2507.22512',
                'license': 'Apache-2.0', 'license_url': 'https://www.apache.org/licenses/LICENSE-2.0',
                'archive_sha256_published': ARCHIVE_SHA256, 'archive_sha256_verified': False,
                'verification': 'HTTPS pinned revision, per-entry ZIP CRC and local SHA-256. Whole archive not downloaded.',
                'selection': {'seed': args.seed, 'count': args.count, 'strategy': 'one image per source patient; source split preserved'},
                'retrieved_at': datetime.now(timezone.utc).isoformat(), 'images': [],
            }
            images = SOURCE_ROOT / 'images'
            images.mkdir(exist_ok=True)
            samples = []
            for number, (patient, info) in enumerate(selected, 1):
                identifier = uuid.uuid5(uuid.NAMESPACE_URL, URL + '#' + info.filename).hex
                path = images / (identifier + PurePosixPath(info.filename).suffix.lower())
                if not path.exists():
                    data = archive.read(info)  # zipfile verifies CRC before the bytes are accepted.
                    with Image.open(io.BytesIO(data)) as image:
                        image.verify()
                    partial = path.with_suffix(path.suffix + '.part')
                    partial.write_bytes(data)
                    partial.replace(path)
                with Image.open(path) as image:
                    image.load()
                    dimensions, format_name = image.size, image.format
                if path.stat().st_size != info.file_size or zlib.crc32(path.read_bytes()) != info.CRC:
                    raise ValueError('Local image differs from archive size/CRC')
                sha256 = digest(path)
                # No source patient crosses a split; imported labels remain unknown.
                split = 'calibration' if '/train/' in info.filename else 'test'
                provenance = f'AlphaDent; {source["source"]}; revision {REVISION}; Apache-2.0. Clinical source claimed by authors; forensic authenticity pending review.'
                samples.append(dict(id=identifier, file=path.relative_to(DATASET_ROOT).as_posix(), sha256=sha256,
                                    group='alphadent_' + patient, split=split, ground_truth=None,
                                    provenance=provenance, verified=False, scope='dental',
                                    reference=None, reference_sha256=None, transformation=None))
                source['images'].append(dict(id=identifier, source_file=info.filename, patient_group='alphadent_' + patient,
                                             source_crc32=f'{info.CRC:08x}', sha256=sha256, size=info.file_size,
                                             width=dimensions[0], height=dimensions[1], format=format_name,
                                             local_file=path.relative_to(DATASET_ROOT).as_posix(), review_status='pending'))
                (SOURCE_ROOT / 'source.json').write_text(json.dumps(source, indent=2), encoding='utf-8')
                print(f'Imported {number}/{len(selected)}; {remote.transferred / 1e6:.1f} MB transferred', flush=True)
            merge_manifest(samples)
            print(f'Manifest updated: {len(samples)} source images, no verified integrity labels.', flush=True)


if __name__ == '__main__':
    main()
