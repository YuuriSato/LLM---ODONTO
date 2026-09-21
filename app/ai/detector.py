from typing import Literal, Protocol

from pydantic import Field
from pathlib import Path
from app.ai.schemas import StrictModel


class DetectorResult(StrictModel):
    provider: str | None
    version: str | None
    status: Literal["disponivel", "desativado", "ausente", "falhou"]
    score: float | None = Field(default=None, ge=0, le=1)
    scale: str | None = None
    conclusion: Literal["alto", "baixo", "inconclusivo"] | None = None
    limitations: list[str] = Field(default_factory=list)


class ExternalDetector(Protocol):
    def analyze(self, image: Path) -> DetectorResult: ...


class DisabledDetector:
    def analyze(self, image: Path) -> DetectorResult:
        return DetectorResult(
            provider=None, version=None, status="desativado",
            limitations=["Detector externo nao configurado; ausencia nao equivale a score baixo."],
        )
