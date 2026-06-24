"""The declarative alias model (docs/planning/07-alias-registry-design.md §3).

An ``Alias`` maps one niva verb to one QGIS algorithm: which positional args it
takes, which ``key=value`` options, which boolean flags, and any values forced on
every call. This is *data* — no algorithm logic lives here. The binder
(``niva.registry.binder``) turns a parsed ``Stage`` + an ``Alias`` into the param
dict ``processing.run`` expects.

Format note: the registry is Python data, **not** YAML — niva keeps near-zero
runtime dependencies (Oscar E1) so it can never destabilise QGIS's own Python, and
a YAML parser would be a dependency. Python dict/dataclass literals are just as
declarative and diffable, and the linter (07-§9) validates them against live QGIS
the same way regardless of format.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Arg:
    """A positional argument. ``name`` is shown in errors; ``param`` is the QGIS
    parameter it fills; ``type`` drives coercion (see binder ``_coerce``)."""

    name: str
    param: str
    type: str = "string"
    required: bool = True


@dataclass
class Option:
    """A ``key=value`` option. ``default`` is the *niva-token form* (e.g. ``"5"``,
    ``"round"``) so it is coerced exactly like user input; ``None`` means omit.
    ``values`` is the enum vocab (word → QGIS int) for ``enum``/``enumlist``."""

    param: str
    type: str = "string"
    default: str | None = None
    values: dict | None = None
    required: bool = False


@dataclass
class Flag:
    """A bare boolean flag. Present → ``param=True``; absent → ``param=False``."""

    param: str


@dataclass
class Alias:
    verb: str
    algorithm: str
    summary: str = ""
    example: str = ""  # a realistic, complex one-liner shown by `describe`/`docs`; if
    # empty, describe synthesises one from the signature (see niva.describe._example_for).
    primary_input: str = "INPUT"
    primary_output: str = "OUTPUT"
    args: list = field(default_factory=list)
    options: dict = field(default_factory=dict)
    flags: dict = field(default_factory=dict)
    forced: dict = field(default_factory=dict)
