"""Runtime helpers shared by development and production launchers."""

from __future__ import annotations

import socket
from typing import Optional


def validate_port(value: int | str) -> int:
    try:
        port = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"PORT must be an integer, got {value!r}") from exc
    if not 1 <= port <= 65535:
        raise ValueError(f"PORT must be between 1 and 65535, got {port}")
    return port


def is_port_available(host: str, port: int) -> bool:
    """Return whether a TCP port can be bound on the requested interface."""

    # Listening on all interfaces is an explicit launcher/container choice; the
    # Compose publication remains loopback-only and public ingress is external.
    bind_host = host
    family = socket.AF_INET6 if ":" in bind_host else socket.AF_INET
    try:
        with socket.socket(family, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind((bind_host, port))
        return True
    except OSError:
        return False


def select_available_port(
    host: str,
    requested: Optional[int | str] = None,
    preferred: int = 7860,
    attempts: int = 100,
) -> int:
    """Select a port while preserving explicit platform port contracts.

    Hosting providers route traffic to the exact value they put in ``PORT``;
    an explicit value is therefore validated and returned unchanged.  Local
    callers that omit a port get the first bindable port in a small range.
    """

    if requested not in (None, ""):
        return validate_port(requested)

    start = validate_port(preferred)
    for port in range(start, min(65536, start + attempts)):
        if is_port_available(host, port):
            return port
    raise RuntimeError(f"No free TCP port found in range {start}-{start + attempts - 1}")
