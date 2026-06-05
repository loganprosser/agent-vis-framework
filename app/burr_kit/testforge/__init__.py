"""Example pluggable TestForge clients.

Provided as a reference for how to wire backend-agnostic clients into a Burr
subsystem. ``FakeTestForgeClient`` is pure Python (greedy pairwise reducer)
and useful for local demos; ``TestForgeHTTPBridgeClient`` talks to a TestForge
MCP HTTP bridge. Neither is imported by the rest of ``burr_kit``.
"""

from app.burr_kit.testforge.fake import FakeTestForgeClient
from app.burr_kit.testforge.http import TestForgeHTTPBridgeClient
from app.burr_kit.testforge.protocol import TestForgeClient

__all__ = ["FakeTestForgeClient", "TestForgeClient", "TestForgeHTTPBridgeClient"]
