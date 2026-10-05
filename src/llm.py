"""Chat client for any OpenAI-compatible API (default: NVIDIA)."""
from __future__ import annotations

import os
import time

import requests

DEFAULT_BASE_URL = "https://integrate.api.nvidia.com/v1"
DEFAULT_MODEL = "nvidia/nemotron-3-super-120b-a12b"


class LLMError(Exception):
    pass


def chat(messages: list[dict], tools: list[dict] | None = None) -> dict:
    key = os.getenv("LLM_API_KEY")
    if not key:
        raise LLMError("LLM_API_KEY is not set")
    url = os.getenv("LLM_BASE_URL", DEFAULT_BASE_URL).rstrip("/") + "/chat/completions"
    body = {
        "model": os.getenv("MODEL_NAME", DEFAULT_MODEL),
        "messages": messages,
        "temperature": 0,
        "max_tokens": 2000,
    }
    if tools:
        body["tools"] = tools

    for attempt in range(3):
        try:
            r = requests.post(url, json=body, headers={"Authorization": f"Bearer {key}"}, timeout=90)
        except requests.RequestException as exc:
            error = str(exc)
        else:
            if r.ok:
                return r.json()["choices"][0]["message"]
            error = f"HTTP {r.status_code}: {r.text[:200]}"
            if r.status_code not in (429, 500, 502, 503, 504):
                break
        time.sleep(2 ** attempt)
    raise LLMError(error)
