"""CodexLean: conservative, reversible context compression for coding agents."""

from .engine import CompressionEngine
from .models import CompressionRequest, CompressionResult, Profile

__all__ = ["CompressionEngine", "CompressionRequest", "CompressionResult", "Profile"]
__version__ = "0.2.0"
