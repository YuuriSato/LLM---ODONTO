from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from io import BytesIO
import json
from pathlib import Path
import tempfile
import threading
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
        uploads = self.folder / "uploads"
        uploads.mkdir()
        for key, value in (("DEVELOPMENT_MODE", False), ("AI_SETTINGS", AISettings(api_key="test")),
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

    def upload(self, fields=None):
        stream = BytesIO()
        Image.new("RGB", (32, 32), "white").save(stream, format="PNG")
        body = b'--test-boundary\r\nContent-Disposition: form-data; name="image"; filename="test.png"\r\nContent-Type: image/png\r\n\r\n' + stream.getvalue() + b"\r\n"
        for key, value in (fields or {}).items():
            body += f'--test-boundary\r\nContent-Disposition: form-data; name="{key}"\r\n\r\n{value}\r\n'.encode()
        body += b"--test-boundary--\r\n"
        return self.request("POST", "/analyze", body, {"Content-Type": "multipart/form-data; boundary=test-boundary"})

    def test_calibration_is_forbidden_without_even_parsing_upload(self):
        status, _ = self.request("POST", "/calibrate")
        self.assertEqual(status, 403)
        self.assertFalse(web.CALIBRATION_FILE.exists())

    def test_provider_override_is_forbidden(self):
        for provider in ("ollama", "local"):
            with self.subTest(provider=provider), patch.object(web, "run_integrity_pipeline") as pipeline:
                status, _ = self.upload({"agent_provider": provider})
                self.assertEqual(status, 403)
                pipeline.assert_not_called()

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

    def test_history_legacy_is_not_reclassified(self):
        for verdict in ("IA_GERADA_EDITADA", "MODIFICADO", "ALTERADA_MANUALMENTE"):
            old = {"verdict": verdict, "report": "Texto original sem score nem diagnostico novo."}
            result = web.normalize_history_item(old)
            self.assertEqual(result["verdict"], verdict)
            self.assertEqual(result["report"], old["report"])
            self.assertNotIn("forensic_score", result)

    def test_details_endpoint_and_traversal(self):
        folder = web.ANALYSIS_DIR / ("a" * 32)
        folder.mkdir(parents=True)
        (folder / "result.json").write_text('{"status":"nao_concluida","verdict":null}')
        status, body = self.request("GET", "/analysis/" + "a" * 32)
        self.assertEqual(status, 200)
        self.assertIsNone(json.loads(body)["verdict"])
        self.assertEqual(self.request("GET", "/analysis/../../.env")[0], 404)


if __name__ == "__main__":
    unittest.main()
