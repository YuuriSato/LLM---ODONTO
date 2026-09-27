"""Download the versioned public Hanoi archive, preserving provenance and bytes."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import time

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.file_lock import file_lock

DATASET = '3253gj88rr'
VERSION = 1
SOURCE = f'https://data.mendeley.com/datasets/{DATASET}/{VERSION}'
API = f'https://data.mendeley.com/public-api/datasets/{DATASET}'
EXPECTED_SHA256 = '16669f74665ff0deca6ddd25feb0d233e52fdc2313265465bf91731af1e8956b'
ROOT = Path(__file__).resolve().parents[1] / 'runtime' / 'datasets' / 'sources' / 'hanoi-v1'


def file_hash(path):
    with path.open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()


def download(session, url, target, size, sha256):
    if target.exists():
        if target.stat().st_size != size or file_hash(target) != sha256:
            raise ValueError('Existing archive does not match the published hash; not overwriting.')
        return target
    partial = target.with_suffix(target.suffix + '.part')
    offset = partial.stat().st_size if partial.exists() else 0
    if offset > size:
        raise ValueError('Partial archive larger than the published file.')
    if offset < size:
        headers = {'Accept-Encoding': 'identity'}
        if offset:
            headers['Range'] = f'bytes={offset}-'
        with session.get(url, headers=headers, stream=True, timeout=(20, 90)) as response:
            response.raise_for_status()
            if offset and (response.status_code != 206 or response.headers.get('Content-Range', '').split('/')[0] != f'bytes {offset}-{size-1}'):
                raise ValueError('Server did not honor the resume range; partial file preserved.')
            if not offset and response.status_code != 200:
                raise ValueError('Unexpected partial response for a new download.')
            last_progress = time.monotonic()
            with partial.open('ab' if offset else 'wb') as handle:
                for chunk in response.iter_content(1024 * 1024):
                    if offset + len(chunk) > size:
                        raise ValueError('Download exceeds the declared size.')
                    handle.write(chunk)
                    offset += len(chunk)
                    if time.monotonic() - last_progress >= 15:
                        print(f'Download: {offset / 1e9:.2f}/{size / 1e9:.2f} GB ({100 * offset / size:.1f}%)', flush=True)
                        last_progress = time.monotonic()
    if offset != size or file_hash(partial) != sha256:
        raise ValueError('Archive size/hash mismatch; partial file retained for inspection.')
    partial.replace(target)
    return target


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--download', action='store_true', help='Transfer the 6.55 GB archive; otherwise metadata only.')
    args = parser.parse_args()
    ROOT.mkdir(parents=True, exist_ok=True)
    with file_lock(ROOT / '.download.lock'), requests.Session() as session:
        response = session.get(API + f'/snapshot/{VERSION}', timeout=30)
        response.raise_for_status()
        snapshot = response.json()
        if snapshot['licence']['short_name'] != 'CC BY 4.0':
            raise ValueError('Dataset license changed; review required before downloading.')
        response = session.get(API + '/files', params={'folder_id': 'root', 'version': VERSION, '$start': 0, '$limit': 1000},
                               headers={'Accept': 'application/vnd.mendeley-public-dataset.1+json'}, timeout=30)
        response.raise_for_status()
        files = response.json()
        archive = next(item for item in files if item['filename'] == 'Dataset.rar')
        details = archive['content_details']
        if details['sha256_hash'] != EXPECTED_SHA256:
            raise ValueError('Published archive changed; refusing to silently replace the source version.')
        provenance = {
            'source': SOURCE, 'doi': snapshot['doi'], 'version': VERSION,
            'title': snapshot['name'], 'contributors': snapshot['contributors'],
            'license': snapshot['licence'], 'description': snapshot['description'],
            'retrieved_at': datetime.now(timezone.utc).isoformat(), 'archive': archive,
            'integrity_label': None, 'integrity_label_verified': False,
            'notes': ['Clinical acquisition described by authors is not a forensic guarantee.',
                      'No inference, upload to AI providers, calibration or training is performed by this script.'],
        }
        (ROOT / 'source.json').write_text(json.dumps(provenance, ensure_ascii=False, indent=2), encoding='utf-8')
        print(f'Source: {SOURCE}\nLicense: CC BY 4.0\nSize: {details["size"]} bytes', flush=True)
        if args.download:
            path = download(session, details['download_url'], ROOT / 'Dataset.rar', details['size'], EXPECTED_SHA256)
            print(f'Archive verified: {path}', flush=True)


if __name__ == '__main__':
    main()
