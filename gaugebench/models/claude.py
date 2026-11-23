"""Claude models via the official Anthropic Python SDK.

Credentials are resolved by the SDK (ANTHROPIC_API_KEY env var or an `ant auth login`
profile) — never put keys in code or in this repository.
"""
from __future__ import annotations

import base64

import anthropic

from .base import Model

SYSTEM = ("You are an experienced plant technician reading analogue instruments from photos. "
          "Read the instrument carefully and answer exactly the question asked.")

BLIND_NOTE = "(No image is attached. Answer as best you can anyway.)"


class Claude(Model):
    def __init__(self, model: str = "claude-opus-5-5", effort: str = "medium", blind: bool = False,
                 fallbacks: bool = True):
        self.model = model
        self.effort = effort
        self.blind = blind              # ablation: same question, no image
        self.fallbacks = fallbacks
        self.name = f"{model}{'-' + effort if effort else ''}{'-blind' if blind else ''}"
        self.client = anthropic.Anthropic(max_retries=4)

    def answer(self, task: dict, image_path: str) -> dict:
        content = []
        if not self.blind:
            with open(image_path, "rb") as f:
                data = base64.standard_b64encode(f.read()).decode("utf-8")
            content.append({"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": data}})
            content.append({"type": "text", "text": task["question"]})
        else:
            content.append({"type": "text", "text": f"{BLIND_NOTE}\n\n{task['question']}"})

        kwargs = dict(model=self.model, max_tokens=16000, system=SYSTEM,
                      messages=[{"role": "user", "content": content}])
        if self.effort:
            kwargs["output_config"] = {"effort": self.effort}
        try:
            if self.fallbacks:
                # Server-side refusal fallback: if the model declines, another model finishes the
                # request. We record which model actually served so results stay attributable.
                resp = self.client.beta.messages.create(betas=["server-side-fallback-2026-07-01"],
                                                        fallbacks="default", **kwargs)
            else:
                resp = self.client.messages.create(**kwargs)
        except anthropic.RateLimitError as e:
            return {"text": "", "error": f"rate_limited: {e}"}
        except anthropic.APIStatusError as e:
            return {"text": "", "error": f"api_status_{e.status_code}: {e.message}"}
        except anthropic.APIConnectionError as e:
            return {"text": "", "error": f"connection: {e}"}

        text = "".join(b.text for b in resp.content if b.type == "text")
        iterations = getattr(resp.usage, "iterations", None) or []
        fallback_ran = any(getattr(it, "type", "") == "fallback_message" for it in iterations)
        return {
            "text": text,
            "stop_reason": resp.stop_reason,
            "served_by": resp.model,
            "fallback_ran": fallback_ran,
            "input_tokens": resp.usage.input_tokens,
            "output_tokens": resp.usage.output_tokens,
        }
