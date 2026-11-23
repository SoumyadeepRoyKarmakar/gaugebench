"""Google Gemini models via the official `google-genai` SDK.

Get a free API key at https://aistudio.google.com (free tier has low rate limits).
The SDK reads it from the GEMINI_API_KEY (or GOOGLE_API_KEY) environment variable;
never put keys in code or in this repository.

List the model ids your key can use:  python -m gaugebench list-models gemini
"""
from __future__ import annotations

import os
import time

from google import genai
from google.genai import errors, types

from .base import Model

SYSTEM = ("You are an experienced plant technician reading analogue instruments from photos. "
          "Read the instrument carefully and answer exactly the question asked.")
BLIND_NOTE = "(No image is attached. Answer as best you can anyway.)"
RETRY_CODES = {429, 500, 503, 504}
REQUEST_TIMEOUT_MS = 120_000


class Gemini(Model):
    def __init__(self, model: str, effort: str | None = None, blind: bool = False, max_tries: int = 6):
        self.model = model
        self.effort = effort            # optional thinking level: minimal|low|medium|high (model-dependent)
        self.blind = blind
        self.max_tries = max_tries
        self.name = f"{model}{'-' + effort if effort else ''}{'-blind' if blind else ''}"
        self.client = _client()

    def answer(self, task: dict, image_path: str) -> dict:
        if self.blind:
            contents = [f"{BLIND_NOTE}\n\n{task['question']}"]
        else:
            with open(image_path, "rb") as f:
                img = types.Part.from_bytes(data=f.read(), mime_type="image/png")
            contents = [img, task["question"]]
        cfg = types.GenerateContentConfig(system_instruction=SYSTEM)
        if self.effort:
            cfg.thinking_config = types.ThinkingConfig(thinking_level=self.effort.upper())

        delay = 10.0
        for attempt in range(self.max_tries):
            try:
                resp = self.client.models.generate_content(model=self.model, contents=contents, config=cfg)
                break
            except errors.APIError as e:
                daily_cap = e.code == 429 and "per day" in (e.message or "").lower()
                if e.code in RETRY_CODES and not daily_cap and attempt + 1 < self.max_tries:
                    time.sleep(delay)       # free tier: back off and retry on rate limits / overload
                    delay = min(delay * 2, 120)
                    continue
                return {"text": "", "error": f"api_{e.code}: {e.message}"}
            except Exception as e:          # network errors / request timeouts from the HTTP layer
                if attempt + 1 < self.max_tries:
                    time.sleep(delay)
                    delay = min(delay * 2, 120)
                    continue
                return {"text": "", "error": f"network: {type(e).__name__}: {e}"}

        cand = resp.candidates[0] if resp.candidates else None
        usage = resp.usage_metadata
        return {
            "text": resp.text or "",
            "stop_reason": str(cand.finish_reason) if cand and cand.finish_reason else None,
            "served_by": resp.model_version or self.model,
            "input_tokens": getattr(usage, "prompt_token_count", None),
            "output_tokens": getattr(usage, "candidates_token_count", None),
        }


def list_models() -> list[str]:
    """Model ids available to this key that support generateContent."""
    client = _client()
    out = []
    for m in client.models.list():
        actions = getattr(m, "supported_actions", None) or []
        if not actions or "generateContent" in actions:
            out.append(m.name.removeprefix("models/"))
    return sorted(out)


def _client() -> genai.Client:
    if not (os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")):
        raise SystemExit("No Gemini API key found. Get a free key at https://aistudio.google.com, then run:\n"
                         '  $env:GEMINI_API_KEY = "your-key"      (PowerShell)')
    # 2-minute per-request limit so a stuck or overloaded endpoint fails fast and gets retried
    return genai.Client(http_options=types.HttpOptions(timeout=REQUEST_TIMEOUT_MS))
