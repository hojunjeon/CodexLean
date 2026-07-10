from __future__ import annotations

import math
import re
from functools import lru_cache

_CJK = re.compile(r"[\u3000-\u9fff\uac00-\ud7af\uf900-\ufaff]")


@lru_cache(maxsize=1)
def _tiktoken_backend():
    try:
        import tiktoken  # type: ignore
    except Exception:
        return None, None

    try:
        available = set(tiktoken.list_encoding_names())
    except Exception:
        available = set()

    # tiktoken-offline bundles cl100k data and avoids a first-run network fetch.
    # Prefer it when installed; otherwise use the current Codex-oriented encoding
    # and then the broadly available cl100k fallback.
    order = (
        ("cl100k_base_offline", "tiktoken:cl100k_base_offline"),
        ("o200k_base", "tiktoken:o200k_base"),
        ("cl100k_base", "tiktoken:cl100k_base"),
    )
    for encoding_name, display_name in order:
        if available and encoding_name not in available:
            continue
        try:
            return tiktoken.get_encoding(encoding_name), display_name
        except Exception:
            continue
    return None, None


def _tiktoken_encoder():
    return _tiktoken_backend()[0]


def estimate_tokens(text: str) -> int:
    """Count tokens with tiktoken when installed; otherwise use a disclosed proxy.

    The fallback estimates Latin-heavy text at four UTF-8 bytes/token and CJK
    characters at roughly one token/character. It is suitable for before/after
    comparisons, not provider billing reconciliation.
    """

    enc = _tiktoken_encoder()
    if enc is not None:
        try:
            return len(enc.encode(text, disallowed_special=()))
        except Exception:
            pass

    if not text:
        return 0
    cjk = len(_CJK.findall(text))
    non_cjk_bytes = max(0, len(text.encode("utf-8", "surrogateescape")) - cjk * 3)
    structural = len(re.findall(r"[{}\[\]():,.;<>/=+*|&!`~^%-]", text))
    estimate = cjk + (non_cjk_bytes / 4.0) + (structural / 10.0)
    return max(1, math.ceil(estimate))


def tokenizer_name() -> str:
    return _tiktoken_backend()[1] or "utf8-proxy-v1"
