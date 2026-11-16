"""Model manifest specification, license validation, and configuration schemas."""

import logging
from enum import Enum
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class ModelRole(str, Enum):
    """Supported roles for models in InsightBot."""

    EMBEDDING = "embedding"
    CLASSIFICATION = "classification"
    EMBEDDING_CHALLENGER = "embedding_challenger"
    GENERATION = "generation"


class ModelStatus(str, Enum):
    """Approval lifecycle status of candidate models."""

    APPROVED = "approved"
    EXPERIMENTAL = "experimental"
    DISABLED = "disabled"


class ChunkingConfig(BaseModel):
    """Deterministic document chunking rules."""

    target_tokens_min: int = Field(default=350, ge=50, le=1000)
    target_tokens_max: int = Field(default=450, ge=100, le=2000)
    overlap_tokens: int = Field(default=50, ge=0, le=200)


class ModelSpec(BaseModel):
    """Specification of a pinned local model candidate."""

    model_id: str
    name: str
    role: ModelRole
    status: ModelStatus
    license: str
    revision: str
    sha256: str
    dimensions: int
    max_tokens: int
    recommended_prefix: dict[str, str] = Field(default_factory=dict)
    chunking: ChunkingConfig | None = None
    confidence_threshold: float = 0.65
    taxonomy: list[str] = Field(default_factory=list)
    supported_languages: list[str] = Field(default_factory=lambda: ["ar", "en", "ru"])
    runtime: str
    memory_mb: int
    description: str

    def is_approved(self) -> bool:
        """Check if model is approved for standard operational workflows."""
        return self.status == ModelStatus.APPROVED


class ModelManifest(BaseModel):
    """Full registry of pinned model candidates and execution boundaries."""

    version: str
    updated_at: str
    cache_dir: str
    models: list[ModelSpec]

    def get_model(self, model_id: str) -> ModelSpec | None:
        """Fetch model specification by unique model_id."""
        for m in self.models:
            if m.model_id == model_id:
                return m
        return None

    def get_by_role(self, role: ModelRole, approved_only: bool = False) -> list[ModelSpec]:
        """Fetch models fulfilling a specific operational role."""
        results = [m for m in self.models if m.role == role]
        if approved_only:
            results = [m for m in results if m.status == ModelStatus.APPROVED]
        return results


def load_model_manifest(config_path: Path | str = "configs/models.yaml") -> ModelManifest:
    """Load and validate model manifest from YAML file."""
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Model manifest file not found at: {path}")

    with open(path, "r", encoding="utf-8") as f:
        data: dict[str, Any] = yaml.safe_load(f)

    return ModelManifest.model_validate(data)
