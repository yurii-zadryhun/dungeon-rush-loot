from __future__ import annotations

import json
import os
import sys
import warnings
from contextlib import contextmanager
from typing import Any

from PIL import Image

from .domain import Box, OcrSpan


@contextmanager
def suppress_native_output(enabled: bool = True):
    if not enabled:
        yield
        return
    sys.stdout.flush(); sys.stderr.flush()
    stdout_fd, stderr_fd = os.dup(1), os.dup(2)
    try:
        with open(os.devnull, "w") as devnull:
            os.dup2(devnull.fileno(), 1); os.dup2(devnull.fileno(), 2)
            yield
    finally:
        sys.stdout.flush(); sys.stderr.flush()
        os.dup2(stdout_fd, 1); os.dup2(stderr_fd, 2)
        os.close(stdout_fd); os.close(stderr_fd)


class PaddleOcrEngine:
    def __init__(self, device: str | None, min_confidence: float, quiet: bool = True) -> None:
        self.min_confidence = min_confidence
        self.quiet = quiet
        self.pipeline = self._build_pipeline(device)

    def recognize(self, image: Image.Image) -> list[OcrSpan]:
        spans, _ = self.recognize_with_diagnostics(image)
        return spans

    def recognize_with_diagnostics(self, image: Image.Image) -> tuple[list[OcrSpan], list[OcrSpan]]:
        predictions = self._predict(image)
        raw = [span for prediction in predictions for span in self._spans(prediction, filter_confidence=False)]
        return [span for span in raw if span.score >= self.min_confidence], raw

    def recognize_many_with_diagnostics(
        self, images: list[Image.Image],
    ) -> list[tuple[list[OcrSpan], list[OcrSpan]]]:
        """OCR both popup columns in one Paddle pipeline call if supported."""
        if not images:
            return []
        if not hasattr(self, "pipeline"):
            return [self.recognize_with_diagnostics(image) for image in images]
        try:
            import numpy as np
            arrays = [np.asarray(image.convert("RGB")) for image in images]
            with suppress_native_output(self.quiet):
                predictions = list(self.pipeline.predict(arrays))
            if len(predictions) != len(images):
                raise ValueError("PaddleOCR returned an unexpected batch length.")
        except (TypeError, ValueError, RuntimeError):
            return [self.recognize_with_diagnostics(image) for image in images]
        results = []
        for prediction in predictions:
            raw = self._spans(prediction, filter_confidence=False)
            results.append(([s for s in raw if s.score >= self.min_confidence], raw))
        return results

    def _build_pipeline(self, device: str | None):
        os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")
        warnings.filterwarnings("ignore", message=r"No ccache found.*")
        try:
            with suppress_native_output(True):
                from paddleocr import PaddleOCR
        except ImportError as exc:
            raise RuntimeError("PaddleOCR is not installed.") from exc
        kwargs: dict[str, Any] = {
            "text_detection_model_name": "PP-OCRv6_medium_det",
            "text_recognition_model_name": "PP-OCRv6_medium_rec",
            "use_doc_orientation_classify": False,
            "use_doc_unwarping": False,
            "use_textline_orientation": False,
        }
        if device:
            kwargs["device"] = device
        with suppress_native_output(True):
            return PaddleOCR(**kwargs)

    def _predict(self, image: Image.Image):
        try:
            import numpy as np
        except ImportError as exc:
            raise RuntimeError("numpy is required.") from exc
        with suppress_native_output(self.quiet):
            return list(self.pipeline.predict(np.asarray(image.convert("RGB"))))

    def _spans(self, prediction: Any, *, filter_confidence: bool = True) -> list[OcrSpan]:
        payload = self._prediction_payload(prediction)
        texts = list(payload.get("rec_texts") or [])
        scores = list(payload.get("rec_scores") or [])
        boxes, polys = payload.get("rec_boxes"), payload.get("rec_polys")
        spans: list[OcrSpan] = []
        for index, text in enumerate(texts):
            score = float(scores[index]) if index < len(scores) else 1.0
            box = self._box_at(index, boxes, polys)
            if str(text).strip() and (not filter_confidence or score >= self.min_confidence) and box is not None:
                spans.append(OcrSpan(str(text).strip(), score, box))
        return spans

    @staticmethod
    def _box_at(index: int, boxes: Any, polys: Any) -> Box | None:
        if boxes is not None and index < len(boxes) and len(boxes[index]) >= 4:
            raw = boxes[index]
            return Box(float(raw[0]), float(raw[1]), float(raw[2]), float(raw[3]))
        if polys is None or index >= len(polys):
            return None
        points = polys[index]
        xs, ys = [float(p[0]) for p in points], [float(p[1]) for p in points]
        return Box(min(xs), min(ys), max(xs), max(ys)) if xs and ys else None

    @staticmethod
    def _prediction_payload(prediction: Any) -> dict[str, Any]:
        data: Any = prediction
        json_attr = getattr(prediction, "json", None)
        if json_attr is not None:
            data = json_attr() if callable(json_attr) else json_attr
        if isinstance(data, str):
            data = json.loads(data)
        if not isinstance(data, dict):
            raise RuntimeError(f"Unsupported PaddleOCR result type: {type(data)!r}")
        return data["res"] if isinstance(data.get("res"), dict) else data
