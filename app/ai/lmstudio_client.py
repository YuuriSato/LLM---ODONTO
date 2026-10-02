"""Local, experimental LM Studio integration."""

import base64
from io import BytesIO
import json
import os
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

from PIL import Image

from app.ai.config import AISettings
from app.ai.gemini_client import Generation, ProviderError, image_bytes
from app.ai.evidence_schema import SCHEMA_MODE, bound_integrity_schema
from app.ai.schemas import IntegrityAnalysis, LocalEvidence


TEXT_SCHEMA_MODE = "text-backend-validated-1"
LOCAL_CONCISE_PROMPT = """
Para caber no limite do modelo local, seja extremamente conciso: use no maximo
duas observacoes curtas por lista e uma frase curta por interpretacao. Nao repita
metricas no texto; mantenha-as apenas nas referencias estruturadas.
"""


def lmstudio_image_bytes(path: Path) -> tuple[bytes, str]:
    data, mime = image_bytes(path)
    if mime != "image/webp":
        return data, mime
    with Image.open(BytesIO(data)) as image:
        converted = BytesIO()
        image.convert("RGB").save(converted, format="PNG")
    return converted.getvalue(), "image/png"


def request_json(path: str, payload: dict | None = None, timeout: float = 3):
    host = os.environ.get("LM_STUDIO_HOST", "http://127.0.0.1:11345").rstrip("/")
    headers = {"Content-Type": "application/json"}
    token = os.environ.get("LM_STUDIO_API_KEY", "")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = Request(host + path, data=None if payload is None else json.dumps(payload).encode(), headers=headers)
    with urlopen(request, timeout=timeout) as response:
        return json.load(response)


def inference_timeout(settings: AISettings) -> int:
    configured = os.environ.get("LM_STUDIO_TIMEOUT_SECONDS")
    return max(1, int(configured)) if configured else max(settings.timeout_seconds, 300)


def output_token_limit(settings: AISettings, requested: int | None = None) -> int:
    configured = max(512, int(os.environ.get("LM_STUDIO_MAX_OUTPUT_TOKENS", "2048")))
    return min(requested or settings.max_output_tokens, configured)


def discover_models() -> list[str]:
    payload = request_json("/api/v1/models")
    return list(dict.fromkeys(
        instance["id"]
        for model in payload["models"]
        if model.get("type") == "llm" and model.get("capabilities", {}).get("vision") is True
        for instance in model.get("loaded_instances", [])
        if isinstance(instance.get("id"), str) and instance["id"]
    ))


def model_descriptors() -> list[dict]:
    result = []
    for model in request_json("/api/v1/models")["models"]:
        if model.get("type") != "llm":
            continue
        loaded = model.get("loaded_instances", [])
        for instance in loaded or [{"id": model.get("key", "")}]:
            result.append({"provider": "lmstudio", "model": instance["id"],
                           "vision": model.get("capabilities", {}).get("vision"),
                           "loaded": bool(loaded), "server": os.environ.get("LM_STUDIO_HOST", "http://127.0.0.1:11345"),
                           "context_length": instance.get("config", {}).get("context_length")})
    return result


def analyze(prompt: str, image: Path, model: str) -> str:
    if model not in discover_models():
        raise RuntimeError("Modelo visual nao esta carregado no LM Studio. Atualize os modelos.")
    mime = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}.get(image.suffix.lower())
    if mime is None:
        raise RuntimeError("Formato nao suportado pelo LM Studio.")
    encoded = base64.b64encode(image.read_bytes()).decode("ascii")
    payload = request_json("/v1/chat/completions", {
        "model": model, "stream": False, "temperature": 0.1, "max_tokens": 2048,
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{encoded}"}},
        ]}],
    }, timeout=180)
    content = payload["choices"][0]["message"]["content"]
    if not isinstance(content, str) or not content.strip():
        raise RuntimeError("LM Studio retornou uma resposta vazia.")
    return content


class LMStudioClient:
    """Uses the same evidence validation and backend audit as Gemini."""

    def __init__(self, settings: AISettings):
        self.settings = settings

    def generate(self, prompt: str, system: str, image: Path, reference: Path | None = None,
                 schema: type | None = None, max_output_tokens: int | None = None,
                 evidence: LocalEvidence | None = None) -> Generation:
        settings = self.settings
        settings.validate()
        try:
            if settings.model not in discover_models():
                raise ProviderError("Modelo visual nao esta carregado no LM Studio.", "model_unavailable")
            content = [{"type": "text", "text": prompt}]
            for label, path in [("Imagem submetida a analise", image), ("Referencia opcional, arquivo separado", reference)]:
                if path is None:
                    continue
                data, mime = lmstudio_image_bytes(path)
                content.extend([
                    {"type": "text", "text": label},
                    {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}"}},
                ])
            request = {"model": settings.model, "stream": False, "temperature": 0.1,
                       "max_tokens": output_token_limit(settings, max_output_tokens),
                       "messages": [{"role": "system", "content": system + LOCAL_CONCISE_PROMPT},
                                    {"role": "user", "content": content}]}
            bound = schema is IntegrityAnalysis and evidence is not None
            if schema:
                request["response_format"] = {"type": "json_schema", "json_schema": {
                    "name": "integrity_analysis", "strict": True,
                    "schema": bound_integrity_schema(evidence) if bound else schema.model_json_schema(),
                }}
            schema_mode = SCHEMA_MODE if bound else "base"
            warnings = []
            try:
                response = request_json("/v1/chat/completions", request, inference_timeout(settings))
            except HTTPError as exc:
                detail = exc.read().decode("utf-8", "replace")
                grammar_failed = exc.code == 400 and (
                    "grammar stack" in detail.lower() or "unable to generate parser" in detail.lower()
                )
                if not grammar_failed or "response_format" not in request:
                    raise
                request.pop("response_format")
                request["response_format"] = {"type": "text"}
                response = request_json("/v1/chat/completions", request, inference_timeout(settings))
                schema_mode = TEXT_SCHEMA_MODE
                warnings.append("LM Studio nao aceitou a gramatica; resposta validada integralmente pelo backend.")
            choice = response["choices"][0]
            text = choice["message"]["content"]
            if choice.get("finish_reason") != "stop" or not isinstance(text, str) or not text.strip():
                raise ProviderError("LM Studio retornou resposta vazia ou incompleta.", "incomplete_response")
            return Generation(text, settings.model, response.get("model"), "STOP", warnings,
                              schema_mode=schema_mode)
        except ProviderError:
            raise
        except HTTPError as exc:
            code = {401: "authentication", 403: "authentication", 404: "model_unavailable", 429: "quota"}.get(exc.code, "provider_error")
            raise ProviderError(f"LM Studio recusou a requisicao (HTTP {exc.code}). Sem fallback.", code) from exc
        except (TimeoutError, URLError) as exc:
            code = "timeout" if isinstance(exc, TimeoutError) or isinstance(getattr(exc, "reason", None), TimeoutError) else "unavailable"
            raise ProviderError("Nao foi possivel concluir a comunicacao com LM Studio.", code) from exc
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise ProviderError("Resposta de transporte invalida do LM Studio.", "invalid_response") from exc
