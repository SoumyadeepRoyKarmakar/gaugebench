from __future__ import annotations


class Model:
    """A model under test. `answer` gets the task record and the image path and
    returns {"text": <raw model output>, ...optional metadata}."""

    name = "model"

    def answer(self, task: dict, image_path: str) -> dict:  # pragma: no cover - interface
        raise NotImplementedError
