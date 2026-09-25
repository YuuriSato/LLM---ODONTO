import unittest
from pathlib import Path
from unittest.mock import patch

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
