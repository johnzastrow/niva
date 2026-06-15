"""Connection references (docs/planning/02, use_cases.md).

niva reaches databases through **named QGIS connections** (`@conn`) — the ones the
user has already configured in QGIS. niva passes only the *name* to the backend,
which resolves host/credentials from QGIS's own connection store. **niva never
sees, stores, logs, or transmits credentials** — that is a hard security boundary
(global CLAUDE.md §1/§14): the connection store is the single source of truth.

Syntax:
- ``@conn``                 — a bare connection (for ``sql @conn "…"``)
- ``@conn.table``           — a table in the connection's default schema
- ``@conn.schema.table``    — a schema-qualified table
"""

from __future__ import annotations


def is_connection_ref(token: str) -> bool:
    return token.startswith("@")


def parse_connection_ref(token: str):
    """Return ``(conn, schema, table)``; ``schema``/``table`` are None when absent.

    Raises ``ValueError`` on an empty/`@`-only reference."""
    body = token[1:]
    if not body:
        raise ValueError("empty connection reference (`@`)")
    parts = body.split(".")
    conn = parts[0]
    if not conn:
        raise ValueError(f"missing connection name in `{token}`")
    if len(parts) == 1:
        return conn, None, None
    if len(parts) == 2:
        return conn, None, parts[1]
    return conn, parts[1], ".".join(parts[2:])
