"""Only module allowed to access the Gemini SDK."""
from dataclasses import dataclass
from io import BytesIO
import time
from pathlib import Path

from google import genai
from google.genai import types
from PIL import Image

from app.ai.config import AISettings


class ProviderError(RuntimeError):
    def __init__(self, message: str, code: str = "provider_error"):
        super().__init__(message)
        self.code = code


@dataclass
class Generation:
    text: str
    requested_model: str
    returned_model: str | None
    finish_reason: str
    cleanup_warnings: list[str]


def provider_schema(schema: type) -> dict:
    # The Gemini response_schema dialect rejects additionalProperties;
    # Pydantic still rejects unexpected properties when validating the response.
    def convert(value):
        if isinstance(value, dict):
            return {key: convert(item) for key, item in value.items() if key != "additionalProperties"}
        if isinstance(value, list):
            return [convert(item) for item in value]
        return value
    return convert(schema.model_json_schema())


def image_bytes(path: Path) -> tuple[bytes, str]:
    with Image.open(path) as image:
        mime = {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp"}.get(image.format)
        if mime:
            return path.read_bytes(), mime
        if image.format != "BMP":
            raise ProviderError("Formato de imagem nao suportado.", "invalid_image")
        buffer = BytesIO()
        image.save(buffer, format="PNG")
        return buffer.getvalue(), "image/png"


class GeminiClient:
    def __init__(self, settings: AISettings):
        self.settings = settings

    def generate(self, prompt: str, system: str, image: Path, reference: Path | None = None,
                 schema: type | None = None, max_output_tokens: int | None = None) -> Generation:
        settings = self.settings
        if not settings.api_key:
            raise ProviderError("GEMINI_API_KEY nao configurada.", "missing_key")
        resources = []
        warnings: list[str] = []
        client = None
        try:
            client = genai.Client(api_key=settings.api_key, http_options=types.HttpOptions(
                timeout=settings.timeout_seconds * 1000, retry_options=types.HttpRetryOptions(attempts=1)))
            images = [("Imagem submetida a analise", image)]
            if reference:
                images.append(("Imagem de referencia opcional, distinta da imagem analisada", reference))
            encoded = [(label, *image_bytes(path)) for label, path in images]
            inline = sum(len(data) for _, data, _ in encoded) + len(prompt.encode("utf-8")) < 10_000_000
            contents = [prompt]
            for label, data, mime in encoded:
                contents.append(label)
                if inline:
                    contents.append(types.Part.from_bytes(data=data, mime_type=mime))
                else:
                    remote = client.files.upload(file=BytesIO(data), config=types.UploadFileConfig(mime_type=mime))
                    resources.append(remote.name)
                    deadline = time.monotonic() + settings.timeout_seconds
                    while str(getattr(remote.state, "value", remote.state)) == "PROCESSING":
                        if time.monotonic() >= deadline:
                            raise ProviderError("Tempo esgotado preparando imagem no Gemini.", "timeout")
                        time.sleep(0.5)
                        remote = client.files.get(name=remote.name)
                    if str(getattr(remote.state, "value", remote.state)) == "FAILED":
                        raise ProviderError("Gemini nao conseguiu processar a imagem.", "invalid_image")
                    contents.append(types.Part.from_uri(file_uri=remote.uri, mime_type=mime))
            config = types.GenerateContentConfig(
                system_instruction=system, temperature=0.1,
                max_output_tokens=max_output_tokens or settings.max_output_tokens,
                response_mime_type="application/json" if schema else "text/plain",
                response_schema=provider_schema(schema) if schema else None,
            )
            response = client.models.generate_content(model=settings.model, contents=contents, config=config)
            text = response.text or ""
            candidates = response.candidates or []
            finish = getattr(candidates[0], "finish_reason", None) if candidates else None
            finish = str(getattr(finish, "value", finish) or "UNKNOWN")
            if finish != "STOP" or not text.strip():
                raise ProviderError("Gemini retornou resposta vazia, bloqueada ou incompleta.", "incomplete_response")
            return Generation(text.strip(), settings.model, getattr(response, "model_version", None), finish, warnings)
        except ProviderError:
            raise
        except Exception as exc:
            code = getattr(exc, "code", None)
            if code == 404:
                raise ProviderError(f"Modelo {settings.model} indisponivel para gerar conteudo. Nenhum modelo alternativo foi usado.", "model_unavailable") from exc
            if code in (401, 403):
                raise ProviderError("Gemini recusou a autenticacao ou permissao da chave.", "authentication") from exc
            if code == 429:
                raise ProviderError("Cota ou limite de requisicoes do Gemini atingido.", "quota") from exc
            raise ProviderError(f"Falha de comunicacao com Gemini ({code or type(exc).__name__}).", "provider_error") from exc
        finally:
            for name in resources:
                try:
                    client.files.delete(name=name)
                except Exception:
                    warnings.append(f"Falha ao remover arquivo remoto temporario: {name}")
            if client is not None:
                try:
                    client.close()
                except Exception:
                    warnings.append("Falha ao fechar cliente Gemini.")
