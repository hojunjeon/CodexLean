from __future__ import annotations

from typing import Protocol

from ..models import Candidate, CompressionRequest


class OutputFilter(Protocol):
    def compress(self, text: str, request: CompressionRequest, confidence: float) -> Candidate:
        ...
