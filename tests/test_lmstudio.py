import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError

from app.ai import lmstudio_client as client
from app import web_alteracao as web


class LMStudioTests(unittest.TestCase):
    def test_only_loaded_vision_instances(self):
        payload = {"models": [
            {"type": "llm", "capabilities": {"vision": True}, "loaded_instances": [{"id": "medgemma"}]},
            {"type": "embedding", "loaded_instances": [{"id": "embedding"}]},
            {"type": "llm", "capabilities": {"vision": True}, "loaded_instances": []},
            {"type": "llm", "loaded_instances": [{"id": "text-only"}]},
        ]}
        with patch.object(client, "request_json", return_value=payload):
            self.assertEqual(client.discover_models(), ["medgemma"])

    def test_production_does_not_discover_or_execute_local(self):
        with patch.object(web, "DEVELOPMENT_MODE", False), patch.object(client, "discover_models") as discover:
            self.assertEqual(web.model_catalog()["local_models"], [])
            with self.assertRaises(RuntimeError):
                web.analyze_image(Path("unused.png"), use_llm=True, agent_provider="lmstudio", model="medgemma")
            discover.assert_not_called()

    def test_discovery_failure_does_not_hide_gemini(self):
        with patch.object(web, "DEVELOPMENT_MODE", True), patch.object(client, "model_descriptors", side_effect=TimeoutError):
            catalog = web.model_catalog()
            self.assertIn("gemini-flash-latest", catalog["models"])
            self.assertIn("indisponivel", catalog["lmstudio_status"])

    def test_unloaded_model_is_rejected(self):
        with patch.object(client, "discover_models", return_value=[]):
            with self.assertRaises(RuntimeError):
                client.analyze("test", Path("unused.png"), "missing")

    def test_structured_call_keeps_original_image_and_separate_reference(self):
        import base64
        from tempfile import TemporaryDirectory
        from PIL import Image
        from app.ai.config import AISettings
        from app.ai.schemas import IntegrityAnalysis
        with TemporaryDirectory() as folder:
            image = Path(folder) / 'image.png'
            Image.new('RGB', (32, 32), 'white').save(image)
            response = {'model': 'medgemma', 'choices': [{'message': {'content': '{}'}, 'finish_reason': 'stop'}]}
            with patch.object(client, 'discover_models', return_value=['medgemma']), patch.object(client, 'request_json', return_value=response) as request:
                result = client.LMStudioClient(AISettings(provider='lmstudio', model='medgemma', development=True)).generate('evidence', 'system', image, image, schema=IntegrityAnalysis)
            payload = request.call_args.args[1]
            self.assertEqual(payload['response_format']['type'], 'json_schema')
            images = [part['image_url']['url'] for part in payload['messages'][1]['content'] if part['type'] == 'image_url']
            self.assertEqual(len(images), 2)
            self.assertEqual(base64.b64decode(images[0].split(',')[1]), image.read_bytes())
            self.assertEqual(result.returned_model, 'medgemma')

    def test_webp_is_converted_to_png_for_local_multimodal_request(self):
        from tempfile import TemporaryDirectory
        from PIL import Image
        with TemporaryDirectory() as folder:
            image = Path(folder) / 'image.webp'
            Image.new('RGB', (16, 16), 'white').save(image)
            data, mime = client.lmstudio_image_bytes(image)
            self.assertEqual(mime, 'image/png')
            self.assertTrue(data.startswith(b'\x89PNG'))

    def test_grammar_engine_failure_retries_as_backend_validated_text(self):
        from tempfile import TemporaryDirectory
        from PIL import Image
        from app.ai.config import AISettings
        from app.ai.schemas import IntegrityAnalysis
        error = HTTPError('http://local', 400, 'bad', {}, BytesIO(
            b'{"error":"Unexpected empty grammar stack after accepting piece"}'))
        response = {'model': 'medgemma', 'choices': [{'message': {'content': '{}'}, 'finish_reason': 'stop'}]}
        with TemporaryDirectory() as folder:
            image = Path(folder) / 'image.png'
            Image.new('RGB', (16, 16), 'white').save(image)
            with patch.object(client, 'discover_models', return_value=['medgemma']), patch.object(
                client, 'request_json', side_effect=[error, response]
            ) as request:
                result = client.LMStudioClient(AISettings(provider='lmstudio', model='medgemma', development=True)).generate(
                    'evidence', 'system', image, schema=IntegrityAnalysis
                )
        self.assertEqual(request.call_count, 2)
        self.assertEqual(request.call_args.args[1]['response_format'], {'type': 'text'})
        self.assertEqual(result.schema_mode, client.TEXT_SCHEMA_MODE)
        self.assertTrue(result.cleanup_warnings)

    def test_local_timeout_and_output_are_bounded_for_slow_inference(self):
        from app.ai.config import AISettings
        settings = AISettings(provider='lmstudio', model='medgemma', development=True, timeout_seconds=30)
        with patch.dict('os.environ', {}, clear=True):
            self.assertEqual(client.inference_timeout(settings), 300)
        with patch.dict('os.environ', {'LM_STUDIO_TIMEOUT_SECONDS': '45'}):
            self.assertEqual(client.inference_timeout(settings), 45)

    def test_local_pipeline_always_validates_and_audits(self):
        from tempfile import TemporaryDirectory
        from PIL import Image
        from unittest.mock import Mock
        from app.ai.config import AISettings
        from app.ai.pipeline import run_integrity_pipeline
        from test_integrity_pipeline import sample_evidence, sample_analysis
        with TemporaryDirectory() as folder:
            image = Path(folder) / 'image.png'
            Image.new('RGB', (32, 32), 'white').save(image)
            evidence = sample_evidence()
            analyzer = Mock(calls=[])
            analyzer.analyze_integrity.return_value = sample_analysis(evidence)
            with patch('app.ai.pipeline.collect_evidence', return_value=evidence):
                result = run_integrity_pipeline(image, settings=AISettings(provider='lmstudio', model='medgemma', development=True),
                                                cache_dir=Path(folder) / 'cache', analyzer=analyzer)
            self.assertEqual(result['audit_status'], 'executada')
            self.assertEqual(result['status'], 'concluida')
            self.assertTrue(result['experimental'])
            analyzer.analyze_integrity.assert_called_once()
