from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from io import BytesIO
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from PIL import Image

from app import web_alteracao as web
from app.ai.config import AISettings


class WebIntegrityTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.folder = Path(temporary.name)
        queue_patch = patch.object(web, "JOB_QUEUE", None)
        queue_patch.start()
        self.addCleanup(queue_patch.stop)
        self.addCleanup(lambda: web.JOB_QUEUE.close() if web.JOB_QUEUE else None)
        uploads = self.folder / "uploads"
        uploads.mkdir()
        for key, value in (("DEVELOPMENT_MODE", False), ("AI_SETTINGS", AISettings(api_key="test")),
                           ("RUNTIME_DIR", self.folder),
                           ("UPLOAD_DIR", uploads), ("ANALYSIS_DIR", self.folder / "cache"),
                           ("HISTORY_FILE", self.folder / "history.json"), ("CALIBRATION_FILE", self.folder / "calibration.json")):
            patcher = patch.object(web, key, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), web.PeritoHandler)
        worker = threading.Thread(target=self.server.serve_forever, daemon=True)
        worker.start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.port = self.server.server_address[1]

    def request(self, method, path, body=None, headers=None):
        connection = HTTPConnection("127.0.0.1", self.port, timeout=5)
        try:
            connection.request(method, path, body, headers or {})
            response = connection.getresponse()
            return response.status, response.read()
        finally:
            connection.close()

    def upload(self, fields=None, extra_headers=None, *, path="/analyze", reference=False):
        stream = BytesIO()
        Image.new("RGB", (32, 32), "white").save(stream, format="PNG")
        body = b'--test-boundary\r\nContent-Disposition: form-data; name="image"; filename="test.png"\r\nContent-Type: image/png\r\n\r\n' + stream.getvalue() + b"\r\n"
        for key, value in (fields or {}).items():
            body += f'--test-boundary\r\nContent-Disposition: form-data; name="{key}"\r\n\r\n{value}\r\n'.encode()
        if reference:
            original = BytesIO()
            Image.new("RGB", (32, 32), "gray").save(original, format="PNG")
            body += b'--test-boundary\r\nContent-Disposition: form-data; name="original_image"; filename="reference.png"\r\nContent-Type: image/png\r\n\r\n' + original.getvalue() + b"\r\n"
        body += b"--test-boundary--\r\n"
        return self.request("POST", path, body, {"Content-Type": "multipart/form-data; boundary=test-boundary", **(extra_headers or {})})

    def test_calibration_does_not_invent_reference_authenticity(self):
        for label in ("MODIFICADO", "IA_GERADA_EDITADA"):
            with self.subTest(label=label), patch.object(web, "DEVELOPMENT_MODE", True):
                status, body = self.upload({"label": label}, path="/calibrate", reference=True)
                self.assertEqual(status, 200, body)
                entries = web.load_calibration()
                self.assertEqual(len(entries), 1)
                entry = next(iter(entries.values()))
                self.assertEqual(entry["label"], label)
                self.assertIsNone(entry["reference_label"])
                self.assertNotIn(entry["original_sha256"], entries)
                self.assertIn("comparison_features", entry)
                self.assertEqual(json.loads(body)["status"], "experimental")

    def test_reference_keeps_existing_label_and_provenance(self):
        original = BytesIO()
        Image.new("RGB", (32, 32), "gray").save(original, format="PNG")
        from hashlib import sha256
        key = sha256(original.getvalue()).hexdigest().upper()
        previous = {"label": "IA_GERADA_EDITADA", "provenance": "Known synthetic fixture"}
        web.save_calibration({key: previous})
        with patch.object(web, "DEVELOPMENT_MODE", True):
            status, body = self.upload({"label": "MODIFICADO"}, path="/calibrate", reference=True)
        self.assertEqual(status, 200, body)
        entries = web.load_calibration()
        self.assertEqual(entries[key], previous)
        edited = next(entry for sha, entry in entries.items() if sha != key)
        self.assertEqual(edited["reference_label"], previous["label"])

    def test_held_out_image_and_reference_are_blocked_using_real_hashes(self):
        from app.evaluation import digest
        dataset = self.folder / 'datasets'
        dataset.mkdir()
        for color in ('white', 'gray'):
            with self.subTest(protected=color):
                image = dataset / 'held-out.png'
                Image.new('RGB', (32, 32), color).save(image)
                sample = dict(id='held-out', file=image.name, sha256=digest(image),
                              group='held-out', split='test', ground_truth=None,
                              verified=False, scope='engineering', provenance='Fixture')
                (dataset / 'manifest.json').write_text(json.dumps(dict(schema_version='1.0', samples=[sample])))
                with patch.object(web, 'DEVELOPMENT_MODE', True):
                    status, body = self.upload({'label': 'MODIFICADO'}, path='/calibrate', reference=True)
                self.assertEqual(status, 400, body)
                self.assertIn('reservada para teste', json.loads(body)['error'])
                self.assertFalse(web.CALIBRATION_FILE.exists())
                self.assertEqual(list(web.UPLOAD_DIR.iterdir()), [])

    def test_calibration_is_forbidden_without_even_parsing_upload(self):
        status, _ = self.request("POST", "/calibrate")
        self.assertEqual(status, 403)
        self.assertFalse(web.CALIBRATION_FILE.exists())

    def test_disconnected_browser_does_not_raise_internal_server_error(self):
        handler = object.__new__(web.PeritoHandler)
        for error in (ConnectionAbortedError, ConnectionResetError, BrokenPipeError):
            with patch('http.server.BaseHTTPRequestHandler.handle', side_effect=error):
                handler.handle()
                self.assertTrue(handler.close_connection)
        with patch('http.server.BaseHTTPRequestHandler.handle', side_effect=ValueError('Unexpected')), self.assertRaises(ValueError):
            handler.handle()

    def test_provider_override_is_forbidden(self):
        for provider in ("ollama", "local"):
            with self.subTest(provider=provider), patch.object(web, "run_integrity_pipeline") as pipeline:
                status, _ = self.upload({"agent_provider": provider})
                self.assertEqual(status, 403)
                pipeline.assert_not_called()
                self.assertEqual(list(web.UPLOAD_DIR.iterdir()), [])

    def test_false_llm_flag_does_not_bypass_production_pipeline(self):
        result = {"schema_version": "2.0", "analysis_id": "a" * 32, "status": "nao_concluida",
                  "verdict": None, "model": "gemini-flash-latest", "report": "Indisponivel", "error": "Modelo indisponivel", "error_code": "model_unavailable"}
        with patch.object(web, "run_integrity_pipeline", return_value=result) as pipeline, patch.object(web, "analyze_forensics") as legacy:
            status, body = self.upload({"use_llm": "0"})
        self.assertEqual(status, 503)
        pipeline.assert_called_once()
        legacy.assert_not_called()
        payload = json.loads(body)
        self.assertIsNone(payload["verdict"])
        self.assertIsNone(web.load_history()[0]["verdict"])
        self.assertEqual(web.load_history()[0]["status"], "nao_concluida")

    def test_agents_exclude_development_providers(self):
        status, body = self.request("GET", "/agents")
        self.assertEqual(status, 200)
        data = json.loads(body)
        self.assertFalse(data["development_mode"])
        self.assertEqual([a["provider"] for a in data["agents"]], ["gemini"])
        self.assertEqual(data["agents"][0]["state"], "configurado")
        self.assertIn("gemini-2.5-flash", data["models"])

    def test_selected_model_reaches_pipeline_without_changing_default(self):
        default = web.AI_SETTINGS.model
        with patch.object(web, "run_integrity_pipeline", return_value={}) as pipeline:
            web.analyze_image(Path("test.png"), model="gemini-2.5-flash")
        self.assertEqual(pipeline.call_args.kwargs["settings"].model, "gemini-2.5-flash")
        self.assertEqual(web.AI_SETTINGS.model, default)
        pipeline.call_args.kwargs["settings"].validate_production()

    def test_unknown_model_is_rejected(self):
        with patch.object(web, "run_integrity_pipeline") as pipeline:
            status, _ = self.upload({"model": "unknown-model"})
        self.assertEqual(status, 400)
        pipeline.assert_not_called()
        self.assertEqual(list(web.UPLOAD_DIR.iterdir()), [])

    def test_restart_exposes_interrupted_job_as_failure_over_http(self):
        from app.jobs import JobQueue
        queue = JobQueue(self.folder / 'jobs.sqlite3')
        queue.close()
        identifier = 'd' * 32
        with queue.connect() as db:
            db.execute('INSERT INTO jobs VALUES (?, ?, ?, ?)', (identifier, 'executando', '', '{}'))
        web.JOB_QUEUE = JobQueue(queue.path)
        status, body = self.request('GET', '/jobs/' + identifier)
        self.assertEqual(status, 200)
        job = json.loads(body)
        self.assertEqual(job['state'], 'falhou')
        self.assertNotIn('result', job)

    def test_history_legacy_is_not_reclassified(self):
        for verdict in ("IA_GERADA_EDITADA", "MODIFICADO", "ALTERADA_MANUALMENTE"):
            old = {"verdict": verdict, "report": "Texto original sem score nem diagnostico novo."}
            result = web.normalize_history_item(old)
            self.assertEqual(result["verdict"], verdict)
            self.assertEqual(result["report"], old["report"])
            self.assertNotIn("forensic_score", result)

    def test_history_distinguishes_inconclusive_impossible_and_failed(self):
        web.append_history({'id': '1', 'verdict': 'INDETERMINADO', 'status': 'concluida'})
        web.append_history({'id': '2', 'verdict': 'INDETERMINADO', 'status': 'concluida',
                            'conclusion_type': 'impossivel_avaliar'})
        web.append_history({'id': '3', 'verdict': None, 'status': 'nao_concluida'})
        counts = web.history_tab_counts(web.load_history())
        self.assertEqual(counts['inconclusive'], 1)
        self.assertEqual(counts['impossible'], 1)
        self.assertEqual(counts['failed'], 1)

    def test_details_endpoint_and_traversal(self):
        folder = web.ANALYSIS_DIR / ("a" * 32)
        folder.mkdir(parents=True)
        (folder / "result.json").write_text('{"status":"nao_concluida","verdict":null}')
        status, body = self.request("GET", "/analysis/" + "a" * 32)
        self.assertEqual(status, 200)
        self.assertIsNone(json.loads(body)["verdict"])
        self.assertEqual(self.request("GET", "/analysis/../../.env")[0], 404)

    def test_compiled_react_interface_and_assets_are_served(self):
        frontend = self.folder / "dist"
        assets = frontend / "assets"
        assets.mkdir(parents=True)
        (frontend / "index.html").write_text(
            '<title>Sato Company | Análise de Integridade</title>', encoding="utf-8"
        )
        (assets / "app.js").write_text("window.appReady=true", encoding="utf-8")
        with patch.object(web, "FRONTEND_DIST_DIR", frontend):
            status, body = self.request("GET", "/")
            self.assertEqual(status, 200)
            self.assertIn("Sato Company".encode(), body)
            status, body = self.request("GET", "/assets/app.js")
            self.assertEqual(status, 200)
            self.assertEqual(body, b"window.appReady=true")
            self.assertEqual(self.request("GET", "/../.env")[0], 404)

    def test_export_and_model_filter(self):
        folder = web.ANALYSIS_DIR / ('b' * 32)
        folder.mkdir(parents=True)
        payload = {'analysis_id': 'b' * 32, 'local_evidence': {'records': [{'id': 'ela'}]}}
        (folder / 'result.json').write_text(json.dumps(payload), encoding='utf-8')
        status, body = self.request('GET', '/analysis/' + 'b' * 32 + '/export')
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body), payload)
        web.append_history({'id': '1', 'model': 'a', 'verdict': 'REAL'})
        web.append_history({'id': '2', 'model': 'b', 'verdict': 'INDETERMINADO'})
        status, body = self.request('GET', '/history?model=b')
        self.assertEqual(status, 200)
        self.assertEqual([item['id'] for item in json.loads(body)['history']], ['2'])

    def test_cross_origin_request_and_negative_length_rejected(self):
        self.assertEqual(self.request('POST', '/analyze', headers={'Origin': 'https://untrusted.example'})[0], 403)
        status, _ = self.request('POST', '/analyze', headers={'Content-Type': 'multipart/form-data; boundary=test', 'Content-Length': '-1'})
        self.assertEqual(status, 400)

    def test_invalid_image_bytes_never_reach_pipeline(self):
        body = b'--x\r\nContent-Disposition: form-data; name="image"; filename="a.png"\r\n\r\nnot an image\r\n--x--\r\n'
        with patch.object(web, 'run_integrity_pipeline') as pipeline:
            status, _ = self.request('POST', '/analyze', body, {'Content-Type': 'multipart/form-data; boundary=x'})
        self.assertEqual(status, 400)
        pipeline.assert_not_called()
        self.assertEqual(list(web.UPLOAD_DIR.iterdir()), [])

    def test_async_http_runs_pipeline_and_exposes_result(self):
        result = {'schema_version': '2.0', 'analysis_id': 'c' * 32, 'status': 'concluida', 'verdict': 'INDETERMINADO', 'report': 'Test', 'model': 'gemini-flash-latest'}
        with patch.object(web, 'run_integrity_pipeline', return_value=result) as pipeline:
            status, body = self.upload(extra_headers={'Prefer': 'respond-async'})
            self.assertEqual(status, 202)
            identifier = json.loads(body)['job_id']
            deadline = time.monotonic() + 3
            while time.monotonic() < deadline:
                status, body = self.request('GET', '/jobs/' + identifier)
                job = json.loads(body)
                if job['state'] == 'concluida':
                    break
                time.sleep(.02)
        self.assertEqual(job['state'], 'concluida')
        self.assertEqual(job['result']['verdict'], 'INDETERMINADO')
        pipeline.assert_called_once()
        self.assertEqual(len(web.load_history()), 1)

    def test_failed_analysis_can_retry_without_upload_and_preserves_history(self):
        failed = {'schema_version': '2.1', 'analysis_id': 'c' * 32, 'status': 'nao_concluida',
                  'conclusion_type': None, 'verdict': None, 'report': 'Falha', 'error': 'Indisponivel',
                  'model': 'gemini-flash-latest', 'provider': 'gemini'}
        retried = {**failed, 'analysis_id': 'd' * 32, 'status': 'concluida',
                   'conclusion_type': 'inconclusiva', 'verdict': 'INDETERMINADO', 'report': 'Inconclusiva'}
        with patch.object(web, 'run_integrity_pipeline', side_effect=[failed, retried]) as pipeline:
            status, body = self.upload(extra_headers={'Prefer': 'respond-async'})
            self.assertEqual(status, 202)
            first_job = json.loads(body)['job_id']
            deadline = time.monotonic() + 3
            while time.monotonic() < deadline:
                first = json.loads(self.request('GET', '/jobs/' + first_job)[1])
                if first['state'] == 'falhou':
                    break
                time.sleep(.02)
            history_id = first['result']['history_item']['id']
            status, body = self.request('POST', f'/analyses/{history_id}/retry')
            self.assertEqual(status, 202, body)
            second_job = json.loads(body)['job_id']
            while time.monotonic() < deadline:
                second = json.loads(self.request('GET', '/jobs/' + second_job)[1])
                if second['state'] == 'concluida':
                    break
                time.sleep(.02)
        self.assertEqual(pipeline.call_count, 2)
        self.assertEqual(len(web.load_history()), 2)
        self.assertEqual(second['result']['conclusion_type'], 'inconclusiva')

    def test_http_queue_capacity_and_cancel(self):
        from app.jobs import JobQueue
        web.JOB_QUEUE = JobQueue(self.folder / 'jobs.sqlite3', capacity=1)
        gate, started = threading.Event(), threading.Event()
        def operation(cancelled):
            started.set()
            gate.wait(3)
            return {'status': 'concluida'}
        identifier = web.JOB_QUEUE.submit(operation)
        try:
            self.assertTrue(started.wait(2))
            status, _ = self.upload(extra_headers={'Prefer': 'respond-async'})
            self.assertEqual(status, 429)
            self.assertEqual(list(web.UPLOAD_DIR.iterdir()), [])
            status, body = self.request('POST', '/jobs/' + identifier + '/cancel')
            self.assertEqual(status, 200)
            self.assertEqual(json.loads(body)['state'], 'cancelando')
        finally:
            gate.set()
        web.JOB_QUEUE.pending.join()
        self.assertEqual(json.loads(self.request('GET', '/jobs/' + identifier)[1])['state'], 'cancelada')


if __name__ == "__main__":
    unittest.main()
