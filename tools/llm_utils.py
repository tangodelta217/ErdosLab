#!/usr/bin/env python3
"""Shared helpers for manual LLM prompt scaffolding."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Iterable, List

DEFAULT_LLM_MODELS = ["gpt-5.2-pro", "gemini-deepthink"]


def parse_models(env_var: str = "LLM_MODELS") -> List[str]:
    raw = os.getenv(env_var, ",".join(DEFAULT_LLM_MODELS))
    models = [item.strip() for item in raw.split(",") if item.strip()]
    return models or list(DEFAULT_LLM_MODELS)


def sanitize_label(model: str) -> str:
    label = re.sub(r"[^a-z0-9]+", "_", model.lower()).strip("_")
    return label or "model"


def write_model_prompts(
    base_dir: Path,
    prompt_text: str,
    response_extension: str = ".md",
    placeholder: str = "# Paste model output below\n\n",
    models: Iterable[str] | None = None,
) -> None:
    base_dir.mkdir(parents=True, exist_ok=True)
    models_list = list(models) if models is not None else parse_models()
    for model in models_list:
        label = sanitize_label(model)
        prompt_path = base_dir / f"{label}_prompt.md"
        response_path = base_dir / f"{label}_response{response_extension}"
        if not prompt_path.exists():
            prompt_path.write_text(
                f"# Model: {model}\n\n{prompt_text.rstrip()}\n",
                encoding="utf-8",
            )
        if not response_path.exists():
            response_path.write_text(placeholder, encoding="utf-8")
