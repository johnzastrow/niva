"""Side-effect utility verbs that are NOT QGIS algorithms.

`notify` (ntfy push) and `email` reach outside QGIS, so their network and credential
handling lives here, isolated from the engine. Design rules:

- **Zero third-party deps** — stdlib ``urllib`` / ``smtplib`` / ``ssl`` only (Oscar E1).
- **Secrets come only from the environment**, never from the flow text, and are never
  returned in errors or logged. The flow text carries *what* to send, not *how to
  authenticate*.
- **Fail closed** — missing/invalid config raises before anything is sent; email
  requires TLS (STARTTLS, or implicit TLS on port 465) and aborts if unavailable.

`catalog` (recursive geospatial inventory) needs QGIS to read each dataset, so it
lives in the engine (it reuses the backend's load/profile); only the report
formatting helper is here so it can be unit-tested without QGIS.
"""

from __future__ import annotations

import os

from .errors import FlowError, OpError


# --- notify (ntfy) -----------------------------------------------------------

def send_ntfy(message: str, *, topic: str | None = None, server: str | None = None,
              title: str | None = None, priority: str | None = None,
              tags: str | None = None, env=None) -> str:
    """POST ``message`` to an ntfy topic. Server/topic/token resolve from args then
    the environment (``NIVA_NTFY_SERVER`` default ``https://ntfy.sh``,
    ``NIVA_NTFY_TOPIC``, ``NIVA_NTFY_TOKEN``). Returns the target URL (no token)."""
    import urllib.request

    env = os.environ if env is None else env
    server = (server or env.get("NIVA_NTFY_SERVER") or "https://ntfy.sh").rstrip("/")
    topic = topic or env.get("NIVA_NTFY_TOPIC")
    if not topic:
        raise FlowError('notify needs a topic: `notify "message" to=<topic>` '
                        "or set NIVA_NTFY_TOPIC")
    url = f"{server}/{topic}"
    headers = {"Content-Type": "text/plain; charset=utf-8"}
    if title:
        headers["Title"] = title
    if priority:
        headers["Priority"] = str(priority)
    if tags:
        headers["Tags"] = tags
    token = env.get("NIVA_NTFY_TOKEN")
    if token:  # bearer token from the environment only — never echoed
        headers["Authorization"] = f"Bearer {token}"

    req = urllib.request.Request(url, data=message.encode("utf-8"),
                                 headers=headers, method="POST")
    try:
        kwargs = {"timeout": 15}
        if url.lower().startswith("https://"):
            import ssl
            kwargs["context"] = ssl.create_default_context()
        with urllib.request.urlopen(req, **kwargs) as resp:
            resp.read()
    except Exception as exc:  # network / HTTP error — no secret in the message
        raise OpError(f"notify failed: {exc}", algorithm="notify",
                      params={"server": server, "topic": topic}, backend="ntfy")
    return url


# --- email (SMTP) ------------------------------------------------------------

def send_email(*, to: str, subject: str = "", body: str = "",
               attach: str | None = None, env=None) -> str:
    """Send an email via SMTP. Connection + credentials come **only** from the
    environment: ``NIVA_SMTP_HOST`` (required), ``NIVA_SMTP_PORT`` (default 587),
    ``NIVA_SMTP_USER``, ``NIVA_SMTP_PASSWORD``, ``NIVA_SMTP_FROM`` (default = user).
    TLS is required (STARTTLS, or implicit TLS on port 465). Returns the recipient."""
    import smtplib
    import ssl
    from email.message import EmailMessage

    env = os.environ if env is None else env
    if not to:
        raise FlowError("email needs a recipient: `email to=<address>`")
    user = env.get("NIVA_SMTP_USER")
    password = env.get("NIVA_SMTP_PASSWORD")
    sender = env.get("NIVA_SMTP_FROM") or user
    host = env.get("NIVA_SMTP_HOST")
    port_str = env.get("NIVA_SMTP_PORT")

    # Gmail is the common case: if the sender is a Gmail address and no host is set,
    # default to Gmail's SMTP. Gmail requires an *App Password* (with 2-Step
    # Verification on), NOT the account password — set it as NIVA_SMTP_PASSWORD.
    addr = (sender or "").lower()
    if not host and addr.endswith(("@gmail.com", "@googlemail.com")):
        host = "smtp.gmail.com"
        port_str = port_str or "587"
    if not host:
        raise FlowError("email needs SMTP config in the environment: set "
                        "NIVA_SMTP_HOST (and NIVA_SMTP_USER / NIVA_SMTP_PASSWORD / "
                        "NIVA_SMTP_FROM). For Gmail, set NIVA_SMTP_USER/FROM to your "
                        "@gmail.com address and NIVA_SMTP_PASSWORD to a Gmail App "
                        "Password. Credentials never come from the flow text.")
    if not sender:
        raise FlowError("email needs a sender: set NIVA_SMTP_FROM or NIVA_SMTP_USER")
    try:
        port = int(port_str or "587")
    except ValueError:
        raise FlowError("email: NIVA_SMTP_PORT must be a number")

    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = to
    msg["Subject"] = subject or "(niva)"
    msg.set_content(body or "")
    if attach:
        attach = os.path.expanduser(attach)
        if not os.path.isfile(attach):
            raise FlowError(f"email attach: no such file: {attach}")
        import mimetypes

        ctype, _ = mimetypes.guess_type(attach)
        maintype, _, subtype = (ctype or "application/octet-stream").partition("/")
        with open(attach, "rb") as fh:
            msg.add_attachment(fh.read(), maintype=maintype, subtype=subtype or "octet-stream",
                               filename=os.path.basename(attach))

    ctx = ssl.create_default_context()
    try:
        if port == 465:  # implicit TLS
            with smtplib.SMTP_SSL(host, port, timeout=30, context=ctx) as smtp:
                if user and password:
                    smtp.login(user, password)
                smtp.send_message(msg)
        else:  # require STARTTLS — fail closed if the server can't upgrade
            with smtplib.SMTP(host, port, timeout=30) as smtp:
                smtp.starttls(context=ctx)
                if user and password:
                    smtp.login(user, password)
                smtp.send_message(msg)
    except Exception as exc:  # never include the password in the error
        raise OpError(f"email failed: {exc}", algorithm="email",
                      params={"to": to, "host": host, "port": port}, backend="smtp")
    return to


# --- catalog formatting (the directory walk + profiling lives in the engine) -

# Extensions that mark a file as geospatial data worth cataloguing. (Plain `.json`
# is deliberately excluded — too broad; GeoJSON uses `.geojson`.)
CATALOG_VECTOR_EXTS = {".gpkg", ".shp", ".geojson", ".gml", ".kml", ".gpx",
                       ".fgb", ".parquet", ".tab", ".mif"}
CATALOG_RASTER_EXTS = {".tif", ".tiff", ".jp2", ".img", ".vrt", ".asc", ".dem",
                       ".hgt", ".bil", ".grd", ".nc"}
# Containers that can hold many layers — catalog enumerates each layer.
CATALOG_MULTILAYER_EXTS = {".gpkg", ".sqlite", ".db"}


def facet_for_ext(ext: str) -> str | None:
    ext = ext.lower()
    if ext in CATALOG_VECTOR_EXTS:
        return "vector"
    if ext in CATALOG_RASTER_EXTS:
        return "raster"
    return None


def format_catalog(root: str, entries: list) -> str:
    """Render the catalogue as Markdown. ``entries`` is a list of
    ``(relpath, facet, profile_dict | None, error | None)``."""
    ok = [e for e in entries if e[2] is not None]
    bad = [e for e in entries if e[2] is None]
    lines = [
        f"# Geospatial data catalog — `{root}`",
        "",
        f"{len(ok)} dataset(s) catalogued"
        + (f", {len(bad)} could not be read" if bad else "") + ".",
        "",
    ]
    for relpath, facet, prof, _err in ok:
        lines.append(f"## {relpath}")
        crs = (prof.get("crs") or {}).get("authid", "(unknown)")
        lines.append(f"- type: **{facet}** · CRS: `{crs}`")
        if facet == "vector":
            geom = prof.get("geometry_type", "?")
            n = prof.get("feature_count", "?")
            lines.append(f"- geometry: {geom} · features: {n}")
            fields = prof.get("fields") or []
            if fields:
                names = ", ".join(f.get("name", "?") for f in fields)
                lines.append(f"- fields ({len(fields)}): {names}")
        else:
            size = prof.get("size") or prof.get("dimensions")
            if size:
                lines.append(f"- size: {size}")
            bands = prof.get("bands")
            if bands is not None:
                lines.append(f"- bands: {bands}")
        ext = prof.get("extent")
        if isinstance(ext, dict):
            lines.append(
                f"- extent: [{ext.get('xmin')}, {ext.get('ymin')}] – "
                f"[{ext.get('xmax')}, {ext.get('ymax')}]"
            )
        lines.append("")
    if bad:
        lines.append("## Could not be read")
        for relpath, facet, _p, err in bad:
            lines.append(f"- `{relpath}` ({facet}): {err}")
        lines.append("")
    return "\n".join(lines)


def format_show(location: str, entries: list, *, is_db: bool = False,
                is_service: bool = False) -> str:
    """Render the `show` listing as a Markdown table. ``entries`` is a list of dicts
    ``{name, kind, type, format, ref}`` (see ``Backend.list_layers``). Keeps it to a
    quick name-and-type glance — the ``ref`` column is copy-pasteable into ``load`` (or,
    for files/services, ``ogrinfo``)."""
    n = len(entries)
    noun = "table" if is_db else "layer" if is_service else "dataset"
    lines = [
        f"# Data at `{location}`",
        "",
        f"{n} {noun}{'' if n == 1 else 's'}.",
        "",
    ]
    if entries:
        lines.append("| Layer | Kind | Type | Format | Source (for `load`) |")
        lines.append("|---|---|---|---|---|")
        for e in entries:
            lines.append(
                f"| {e.get('name', '?')} | {e.get('kind', '?')} | {e.get('type', '?')} "
                f"| {e.get('format', '?')} | `{e.get('ref', '?')}` |"
            )
        lines.append("")
        if is_db:
            lines.append("Load a row with `load <source>`; inspect one with "
                         "`sql @conn \"SELECT … LIMIT 0\"` (credentials stay in QGIS).")
        elif is_service:
            lines.append("WFS / ArcGIS feature layers: `ogrinfo \"<source>\" <layer>`. "
                         "WMS / XYZ are map services — add the endpoint in QGIS.")
        else:
            lines.append("Load a row with `load \"<source>\"`; for more detail run "
                         "`ogrinfo <file> <layer>` or `load \"<source>\" | assess`.")
        # The Source cells are shown in Markdown `backticks` — copy the value *inside* them.
        # The `|` is niva's pipe, so the source must stay quoted; in a shell, quote the whole
        # flow so your shell doesn't eat the quotes or split on `|`:
        lines.append("Tip: copy a Source **without** its surrounding backticks, and quote the "
                     "whole flow for your shell — `niva 'load \"<source>\"'`.")
        examples = _show_examples(entries) if not is_service else []
        if examples:
            lines.append("")
            lines.append("Examples — copy one and run it **in your shell** (in the QGIS dock, "
                         "use just the flow inside the quotes):")
            lines.append("")
            # Wrap each flow as `niva '…'`: the single quotes keep your shell from eating the
            # double quotes or splitting on `|` (niva's pipe), so it pastes and runs as-is.
            lines.extend(f"    niva '{flow}'" for flow in examples)
    else:
        lines.append("_No loadable layers found here._")
    lines.append("")
    return "\n".join(lines)


def _show_examples(entries: list) -> list:
    """Two concrete, runnable `load … | <alias> | save …` flows built from the first usable
    row of a `show` listing — so the reader can copy a real source and pipe it onward."""
    pick = next((e for e in entries if e.get("kind") == "vector"), entries[0])
    ref = pick.get("ref", "")
    # Quote the source if it carries any char that would break an unquoted niva token: a
    # space/tab (token split), `|` (pipe), or `#` (comment) — e.g. a layer/table named
    # `name-with-dash#hash` or `My Roads`. Otherwise the example would silently truncate.
    src = f'"{ref}"' if any(c in ref for c in " \t#|") else ref
    kind = pick.get("kind")
    if kind == "raster":
        return [f"load {src} | hillshade | save hillshade.tif",
                f"load {src} | warp EPSG:3857 | save reprojected.tif"]
    if kind == "table":
        # `assess` always writes to a file — it has no stdout form — so the example must
        # name one, or copying it yields a flow that errors (`assess needs an output`).
        return [f"load {src} | assess to assessment.md",
                f"load {src} | save extract.gpkg"]
    # Reproject before buffering so `100m` is valid whatever the input CRS — a geographic
    # (degrees) layer can't be buffered by a metric distance directly. Both examples then run
    # on any vector source; `centroid` is CRS-agnostic so it stays a clean second example.
    return [f"load {src} | reproject EPSG:3857 | buffer 100m | save buffered.gpkg",
            f"load {src} | centroid | save points.gpkg"]
