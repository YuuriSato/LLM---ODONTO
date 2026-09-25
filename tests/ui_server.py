"""Disposable HTTP fixtures for browser tests; never writes to the user's runtime."""
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import sys
import tempfile
import threading

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PIL import Image
from app import web_alteracao as web


def main():
    with tempfile.TemporaryDirectory(prefix='integrity-ui-') as temporary:
        root = Path(temporary)
        web.RUNTIME_DIR = root
        web.UPLOAD_DIR = root / 'uploads'
        web.ANALYSIS_DIR = root / 'analysis_cache'
        web.HISTORY_FILE = root / 'analysis_history.json'
        web.CALIBRATION_FILE = root / 'integrity_calibration.json'
        web.UPLOAD_DIR.mkdir()
        folder = web.ANALYSIS_DIR / ('e' * 32)
        folder.mkdir(parents=True)
        (folder / 'result.json').write_text(json.dumps({
            'analysis_id': folder.name, 'local_evidence': {'schema_version': '1.0', 'records': []},
        }), encoding='utf-8')
        Image.new('RGB', (320, 240), '#008877').save(web.UPLOAD_DIR / 'ui-fixture.png')
        server = ThreadingHTTPServer(('127.0.0.1', 0), web.PeritoHandler)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        print(f'UI_TEST_URL=http://127.0.0.1:{server.server_port}', flush=True)
        try:
            # The test controller closes stdin in its finally block.
            sys.stdin.read()
        finally:
            server.shutdown()
            server.server_close()
            worker.join()
            if web.JOB_QUEUE is not None:
                web.JOB_QUEUE.close()


if __name__ == '__main__':
    main()
