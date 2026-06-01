"""Test harness for the forge hub ↔ spoke contract.

Public surface:

* :class:`FakeForgeHub` — async context-manager that wires forge's
  :class:`InMemoryServicer` + :class:`InMemoryChannel` +
  :class:`GrpcTransportAdapter` around our
  :class:`PlcWorkflowsMpcAdapter`. Drives the full lifecycle
  (``register → configure → start → stream → stop``) through the same
  serialization path the real hub will use, without standing up gRPC.
"""

from __future__ import annotations

from harness.hub import FakeForgeHub

__all__ = ["FakeForgeHub"]
