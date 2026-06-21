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


def resolve_connection_name(token: str, known_names=()):
    """Split an ``@``-reference into ``(conn, rest_parts)``.

    ``conn`` is the **longest dotted prefix** of the reference body that is an
    actually-registered connection name — so a connection whose name contains dots
    (e.g. a GeoPackage/SpatiaLite connection like ``CNYTriData.gpkg``) resolves whole
    instead of being split on its first dot. ``rest_parts`` are the remaining dotted
    components, left for the caller to interpret under its own grammar (``load``/``save``:
    one trailing part is a table, two are schema + table; ``show``: one is a schema scope).

    When nothing matches (or ``known_names`` is empty), falls back to the first segment as
    the connection name, so the backend raises a clear "no such connection" naming exactly
    what the user typed. Raises ``ValueError`` on an empty/`@`-only reference."""
    body = token[1:]
    if not body:
        raise ValueError("empty connection reference (`@`)")
    parts = body.split(".")
    known = set(known_names or ())
    for i in range(len(parts), 0, -1):
        if ".".join(parts[:i]) in known:
            return ".".join(parts[:i]), parts[i:]
    conn = parts[0]
    if not conn:
        raise ValueError(f"missing connection name in `{token}`")
    return conn, parts[1:]


def parse_connection_ref(token: str, known_names=()):
    """Return ``(conn, schema, table)`` under the ``load``/``save`` grammar (one trailing
    component is a table, two are schema + table); ``schema``/``table`` are None when absent.

    ``known_names`` is the set of registered connection names — pass
    ``backend.connection_names()`` so a dotted connection name round-trips (e.g. the Source
    ``show`` prints for a GeoPackage connection). Raises ``ValueError`` on an empty
    reference."""
    conn, rest = resolve_connection_name(token, known_names)
    if not rest:
        return conn, None, None
    if len(rest) == 1:
        return conn, None, rest[0]
    return conn, rest[0], ".".join(rest[1:])


def default_schema(provider: str, schema: str | None) -> str:
    """The effective DB schema for a write or repoint target: an explicit ``schema`` wins;
    otherwise the provider's default — ``public`` for PostgreSQL, ``''`` (let the provider
    decide) for SpatiaLite and other file databases."""
    if schema is not None:
        return schema
    return "public" if provider == "postgres" else ""
