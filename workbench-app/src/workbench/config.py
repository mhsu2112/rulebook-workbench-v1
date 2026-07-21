"""Task registry loading (models.yaml). Every AI call site is a named task."""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel, Field


class TaskConfig(BaseModel):
    phase: str
    description: str
    default_model: str
    fallbacks: list[str] = Field(default_factory=list)
    params: dict = Field(default_factory=dict)
    sensitive: bool = False
    structured_output: Optional[str] = None
    skill_version: Optional[str] = None
    must_differ_family_from: list[str] = Field(default_factory=list)


class Settings(BaseModel):
    base_url: str = "https://openrouter.ai/api/v1"
    data_collection: str = "deny"
    zdr_pool_available: bool = True
    contracts_dirs: list[str] = Field(default_factory=list)
    catalog: list[str] = Field(default_factory=list)  # extra selectable models (beyond task defaults)


class Registry(BaseModel):
    settings: Settings
    tasks: dict[str, TaskConfig]
    registry_version: str  # sha256 of the yaml file content
    source_path: str

    def task(self, task_id: str) -> TaskConfig:
        if task_id not in self.tasks:
            raise KeyError(f"Unknown task '{task_id}' — every AI call site must be a named task in models.yaml")
        return self.tasks[task_id]

    def resolve_schema_path(self, filename: str) -> Path:
        base = Path(self.source_path).parent
        for d in self.settings.contracts_dirs:
            candidate = (base / d / filename).resolve()
            if candidate.exists():
                return candidate
        raise FileNotFoundError(
            f"structured_output schema '{filename}' not found in contracts_dirs {self.settings.contracts_dirs}"
        )


def load_registry(path: str | Path) -> Registry:
    p = Path(path)
    raw = p.read_bytes()
    doc = yaml.safe_load(raw)
    return Registry(
        settings=Settings(**(doc.get("settings") or {})),
        tasks={k: TaskConfig(**v) for k, v in (doc.get("tasks") or {}).items()},
        registry_version=hashlib.sha256(raw).hexdigest(),
        source_path=str(p),
    )
