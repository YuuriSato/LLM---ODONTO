from dataclasses import dataclass, field
import os

from app.env_loader import load_project_env

PRIMARY_MODEL = "gemini-flash-latest"
SUPPORTED_MODELS = (PRIMARY_MODEL, "gemini-2.5-flash")
SCHEMA_VERSION = "2.0"
PROMPT_VERSION = "integrity-2.0"


@dataclass(frozen=True)
class AISettings:
    provider: str = "gemini"
    model: str = PRIMARY_MODEL
    api_key: str = field(default="", repr=False)
    development: bool = False
    timeout_seconds: int = 90
    max_output_tokens: int = 8192

    def validate(self) -> None:
        if self.provider == "lmstudio":
            if not self.development:
                raise ValueError("LM Studio exige modo de desenvolvimento.")
            if not self.model:
                raise ValueError("Selecione um modelo visual do LM Studio.")
            return
        self.validate_production()

    def validate_production(self) -> None:
        if self.provider != "gemini" or self.model not in SUPPORTED_MODELS:
            raise ValueError("Producao exige Gemini e um modelo permitido.")
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY nao configurada.")


def get_settings() -> AISettings:
    load_project_env()
    return AISettings(
        provider=os.environ.get("AI_PROVIDER", os.environ.get("LLM_PROVIDER", "gemini")).strip().lower(),
        model=os.environ.get("GEMINI_MODEL", PRIMARY_MODEL).strip(),
        api_key=os.environ.get("GEMINI_API_KEY", ""),
        development=os.environ.get("APP_ENV", "production").lower() == "development",
        timeout_seconds=max(1, int(os.environ.get("AI_TIMEOUT_SECONDS", "90"))),
        max_output_tokens=max(1024, int(os.environ.get("AI_MAX_OUTPUT_TOKENS", "8192"))),
    )
