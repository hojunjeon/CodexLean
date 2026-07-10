from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class Profile(str, Enum):
    """Compression aggressiveness.

    STRICT only removes deterministic presentation noise and repeated lines.
    SAFE applies format-aware filtering with exact recovery and quality guards.
    MAX keeps fewer representative lines; it remains reversible but is not the
    default because the first-pass view can omit context that a model may need.
    """

    STRICT = "strict"
    SAFE = "safe"
    MAX = "max"


@dataclass(slots=True)
class CompressionRequest:
    raw: bytes
    command: tuple[str, ...] = ()
    exit_code: int = 0
    cwd: Path | None = None
    profile: Profile = Profile.SAFE
    kind_hint: str | None = None
    min_bytes: int = 2_048
    min_lines: int = 40
    min_savings_ratio: float = 0.08
    store_original: bool = True


@dataclass(slots=True)
class Candidate:
    text: str
    kind: str
    omitted_lines: int = 0
    critical_lines: tuple[str, ...] = ()
    protected_lines: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()
    confidence: float = 1.0


@dataclass(slots=True)
class CompressionStats:
    raw_bytes: int
    compact_bytes: int
    raw_lines: int
    compact_lines: int
    raw_tokens_est: int
    compact_tokens_est: int

    @property
    def byte_savings(self) -> int:
        return max(0, self.raw_bytes - self.compact_bytes)

    @property
    def byte_savings_ratio(self) -> float:
        if self.raw_bytes == 0:
            return 0.0
        return self.byte_savings / self.raw_bytes

    @property
    def token_savings_est(self) -> int:
        return max(0, self.raw_tokens_est - self.compact_tokens_est)

    @property
    def token_savings_ratio_est(self) -> float:
        if self.raw_tokens_est == 0:
            return 0.0
        return self.token_savings_est / self.raw_tokens_est


@dataclass(slots=True)
class CompressionResult:
    output: bytes
    kind: str
    transformed: bool
    artifact_id: str | None
    fallback_reason: str | None
    stats: CompressionStats
    quality_passed: bool
    notes: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)
