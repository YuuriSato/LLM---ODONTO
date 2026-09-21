from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from PIL import Image
from google.genai.errors import ClientError

from app.ai.config import AISettings, PRIMARY_MODEL
from app.ai.gemini_client import GeminiClient, ProviderError, image_bytes
from app.ai.schemas import IntegrityAnalysis


class GeminiClientTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.image = Path(temporary.name) / "image.png"
        Image.new("RGB", (48, 32), "white").save(self.image)
        patcher = patch("app.ai.gemini_client.genai.Client")
        self.sdk = patcher.start().return_value
        self.addCleanup(patcher.stop)
        self.sdk.models.generate_content.return_value = SimpleNamespace(
            text='{"ok": true}', candidates=[SimpleNamespace(finish_reason="STOP")], model_version=PRIMARY_MODEL,
        )
        self.client = GeminiClient(AISettings(api_key="test-key"))

    def test_exact_model_schema_and_original_image(self):
        result = self.client.generate("Test", "System", self.image, schema=IntegrityAnalysis)
        call = self.sdk.models.generate_content.call_args.kwargs
        self.assertEqual(call["model"], PRIMARY_MODEL)
        self.assertIn("veredito", call["config"].response_schema["properties"])
        self.assertNotIn("additionalProperties", str(call["config"].response_schema))
        self.assertEqual(call["config"].response_mime_type, "application/json")
        self.assertEqual(call["contents"][2].inline_data.data, self.image.read_bytes())
        self.assertEqual(result.returned_model, PRIMARY_MODEL)
        self.sdk.close.assert_called_once()

    def test_no_fallback_for_provider_failures(self):
        for code, error in [(404, "model_unavailable"), (401, "authentication"), (403, "authentication"), (429, "quota"), (500, "provider_error")]:
            with self.subTest(code=code):
                self.sdk.models.generate_content.reset_mock()
                self.sdk.models.generate_content.side_effect = ClientError(code, {"error": {"code": code, "message": "SECRET"}})
                with self.assertRaises(ProviderError) as caught:
                    self.client.generate("Test", "System", self.image)
                self.assertEqual(caught.exception.code, error)
                self.assertNotIn("SECRET", str(caught.exception))
                self.sdk.models.generate_content.assert_called_once()

    def test_truncated_and_empty_responses_are_failures(self):
        for text, finish in [("partial", "MAX_TOKENS"), ("", "STOP"), ("", "SAFETY")]:
            with self.subTest(finish=finish):
                self.sdk.models.generate_content.return_value = SimpleNamespace(text=text, candidates=[SimpleNamespace(finish_reason=finish)])
                with self.assertRaises(ProviderError):
                    self.client.generate("Test", "System", self.image)

    def test_timeout_is_not_retried(self):
        self.sdk.models.generate_content.side_effect = TimeoutError()
        with self.assertRaises(ProviderError):
            self.client.generate("Test", "System", self.image)
        self.sdk.models.generate_content.assert_called_once()

    def test_remote_files_deleted_even_on_api_failure(self):
        self.sdk.files.upload.return_value = SimpleNamespace(name="files/test", uri="test-uri", state="ACTIVE")
        self.sdk.models.generate_content.side_effect = ClientError(404, {"error": {"code": 404}})
        with patch("app.ai.gemini_client.image_bytes", return_value=(b"x" * 10_000_001, "image/png")):
            with self.assertRaises(ProviderError):
                self.client.generate("Test", "System", self.image)
        self.sdk.files.delete.assert_called_once_with(name="files/test")
        self.sdk.close.assert_called_once()

    def test_bmp_lossless_conversion_and_jpeg_unchanged(self):
        for extension in ("bmp", "jpg"):
            path = self.image.with_suffix("." + extension)
            Image.new("RGB", (48, 32), "red").save(path)
            data, mime = image_bytes(path)
            if extension == "jpg":
                self.assertEqual(data, path.read_bytes())
            else:
                from io import BytesIO
                with Image.open(BytesIO(data)) as converted:
                    self.assertEqual(converted.size, (48, 32))
                    self.assertEqual(converted.getpixel((0, 0)), (255, 0, 0))
                self.assertEqual(mime, "image/png")


if __name__ == "__main__":
    unittest.main()
