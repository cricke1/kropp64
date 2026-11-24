"""Inställningar. Läses från miljövariabler med prefixet KONSILIET_."""
from __future__ import annotations

import os
from dataclasses import dataclass, field


def _env(name: str, default: str) -> str:
    return os.environ.get(f"KONSILIET_{name}", default)


@dataclass(frozen=True)
class Settings:
    db_path: str = _env("DB", "~/.konsiliet/konsiliet.db")
    host: str = _env("HOST", "127.0.0.1")
    port: int = int(_env("PORT", "8787"))
    ollama_url: str = _env("OLLAMA", "http://127.0.0.1:11434")
    # Modellval sätts efter mätningarna i bench/. Se bench/RESULTAT.md.
    model_orchestrator: str = _env("MODEL_ORCH", "qwen3.5:9b")
    model_specialist: str = _env("MODEL_SPEC", "medgemma:4b")
    # Enhetstoken för mobilappen. Cloudflare Access skyddar dessutom allt utifrån.
    device_tokens: tuple[str, ...] = field(
        default_factory=lambda: tuple(t for t in _env("DEVICE_TOKENS", "").split(",") if t)
    )


settings = Settings()
