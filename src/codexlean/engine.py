from __future__ import annotations

import os
from pathlib import Path

from .detector import detect_kind
from .filters import get_filter
from .models import (
    CompressionRequest,
    CompressionResult,
    CompressionStats,
)
from .quality import contains_probable_secret, validate_candidate
from .storage import ArtifactStore
from .textutil import decode, encode, is_binary
from .tokens import estimate_tokens


class CompressionEngine:
    """Apply conservative format-aware compression with exact recovery."""

    def __init__(self, store: ArtifactStore | None = None) -> None:
        self.store = store

    @staticmethod
    def _stats(raw: bytes, compact: bytes) -> CompressionStats:
        raw_text = decode(raw)
        compact_text = decode(compact)
        return CompressionStats(
            raw_bytes=len(raw),
            compact_bytes=len(compact),
            raw_lines=len(raw_text.splitlines()),
            compact_lines=len(compact_text.splitlines()),
            raw_tokens_est=estimate_tokens(raw_text),
            compact_tokens_est=estimate_tokens(compact_text),
        )

    def _record(
        self,
        *,
        request: CompressionRequest,
        result: CompressionResult,
    ) -> None:
        if self.store is None:
            return
        try:
            self.store.record_run(
                artifact_id=result.artifact_id,
                command=request.command,
                kind=result.kind,
                profile=request.profile.value,
                transformed=result.transformed,
                quality_passed=result.quality_passed,
                fallback_reason=result.fallback_reason,
                stats=result.stats,
            )
        except Exception:
            # Analytics must never alter the wrapped command's visible output or exit code.
            pass

    def _passthrough(
        self,
        request: CompressionRequest,
        *,
        kind: str,
        reason: str | None,
        quality_passed: bool = True,
        notes: tuple[str, ...] = (),
    ) -> CompressionResult:
        stats = self._stats(request.raw, request.raw)
        result = CompressionResult(
            output=request.raw,
            kind=kind,
            transformed=False,
            artifact_id=None,
            fallback_reason=reason,
            stats=stats,
            quality_passed=quality_passed,
            notes=notes,
        )
        self._record(request=request, result=result)
        return result

    @staticmethod
    def _render(
        candidate_text: str,
        *,
        kind: str,
        artifact_id: str | None,
        raw_lines: int,
        omitted_lines: int,
        exit_code: int,
    ) -> bytes:
        body = candidate_text.rstrip("\n")
        parts: list[str] = []
        if artifact_id:
            view_lines = len(candidate_text.splitlines())
            parts.append(
                f"[codexlean {kind}; exit={exit_code}; lines={raw_lines}->{view_lines}; "
                f"omitted={omitted_lines} | exact: codexlean show {artifact_id}]"
            )
        parts.append(body)
        rendered = "\n".join(part for part in parts if part != "")
        if rendered and not rendered.endswith("\n"):
            rendered += "\n"
        return encode(rendered)

    def compress(self, request: CompressionRequest) -> CompressionResult:
        raw = request.raw
        if not raw:
            return self._passthrough(request, kind=request.kind_hint or "empty", reason="empty output")
        if is_binary(raw):
            return self._passthrough(
                request, kind=request.kind_hint or "binary", reason="binary output protected"
            )

        raw_text = decode(raw)
        raw_lines = len(raw_text.splitlines())
        if len(raw) < request.min_bytes and raw_lines < request.min_lines:
            detection = detect_kind(request.command, raw_text, request.kind_hint)
            return self._passthrough(request, kind=detection.kind, reason="below compression threshold")

        detection = detect_kind(request.command, raw_text, request.kind_hint)
        output_filter = get_filter(detection.kind)
        candidate = output_filter.compress(raw_text, request, detection.confidence)

        # Local persistence is intentionally disabled for probable credentials unless
        # explicitly opted in. Without recovery storage, selective omission is rejected.
        store_allowed = (
            request.store_original
            and self.store is not None
            and (
                not contains_probable_secret(raw_text)
                or os.getenv("CODEXLEAN_STORE_SECRETS") == "1"
            )
        )
        # Selective omission is only safe when the exact original can be fetched.
        # Check this before the remaining quality invariants so the fallback reason
        # is operationally actionable.
        if candidate.omitted_lines > 0 and not store_allowed:
            reason = (
                "probable secret: exact-recovery storage not permitted"
                if contains_probable_secret(raw_text)
                else "exact-recovery store unavailable"
            )
            return self._passthrough(
                request,
                kind=detection.kind,
                reason=reason,
                notes=candidate.notes,
            )

        decision = validate_candidate(
            request,
            raw_text,
            candidate,
            retrieval_available=True,
        )
        if not decision.passed:
            return self._passthrough(
                request,
                kind=detection.kind,
                reason=f"quality guard: {decision.reason}",
                quality_passed=False,
                notes=candidate.notes,
            )

        candidate_bytes = encode(candidate.text)
        changed = candidate_bytes != raw
        if not changed:
            return self._passthrough(
                request,
                kind=detection.kind,
                reason="filter found no safe reduction",
                notes=candidate.notes,
            )

        # Compute the rendered size before writing the artifact, so candidates that
        # fail the net-savings gate do not leave unreachable local data behind.
        artifact_id: str | None = None
        if store_allowed:
            artifact_id = ArtifactStore.artifact_id(raw)[0]

        rendered = self._render(
            candidate.text,
            kind=detection.kind,
            artifact_id=artifact_id,
            raw_lines=raw_lines,
            omitted_lines=candidate.omitted_lines,
            exit_code=request.exit_code,
        )
        stats = self._stats(raw, rendered)

        # Header/recovery instructions can outweigh reductions on small outputs.
        # Never emit a result that is not strictly smaller, even when the caller
        # sets the configured threshold to zero for benchmarking.
        if len(rendered) >= len(raw) or stats.byte_savings_ratio < request.min_savings_ratio:
            return self._passthrough(
                request,
                kind=detection.kind,
                reason=(
                    f"net savings {stats.byte_savings_ratio:.1%} below "
                    f"minimum {request.min_savings_ratio:.1%}"
                ),
                notes=candidate.notes,
            )

        if store_allowed:
            assert self.store is not None
            try:
                actual_id = self.store.put(
                    raw,
                    command=request.command,
                    cwd=request.cwd,
                    exit_code=request.exit_code,
                    kind=detection.kind,
                )
            except Exception:
                # A storage failure cannot be allowed to hide omitted context.
                return self._passthrough(
                    request,
                    kind=detection.kind,
                    reason="exact-recovery store write failed",
                    notes=candidate.notes,
                )
            if actual_id != artifact_id:
                artifact_id = actual_id
                rendered = self._render(
                    candidate.text,
                    kind=detection.kind,
                    artifact_id=artifact_id,
                    raw_lines=raw_lines,
                    omitted_lines=candidate.omitted_lines,
                    exit_code=request.exit_code,
                )
                stats = self._stats(raw, rendered)
                if (
                    len(rendered) >= len(raw)
                    or stats.byte_savings_ratio < request.min_savings_ratio
                ):
                    return self._passthrough(
                        request,
                        kind=detection.kind,
                        reason="collision-expanded recovery ID removed net savings",
                        notes=candidate.notes,
                    )

        result = CompressionResult(
            output=rendered,
            kind=detection.kind,
            transformed=True,
            artifact_id=artifact_id,
            fallback_reason=None,
            stats=stats,
            quality_passed=True,
            notes=candidate.notes,
            metadata={
                "detection_reason": detection.reason,
                "confidence": detection.confidence,
                "omitted_lines": candidate.omitted_lines,
            },
        )
        self._record(request=request, result=result)
        return result
