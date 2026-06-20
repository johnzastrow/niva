"""Remote OWS service listing for the `show` verb — WFS feature types and WMS layers.

This is pure standard-library HTTP + XML (no QGIS, no third-party deps), so it is fully
unit-testable offline by injecting a ``fetch`` callable. The backend (`PyqgisBackend`) just
delegates here; the engine routes a service URL to ``Backend.list_service``.

Security (per the project's secure-coding baseline):
- **XXE / entity-expansion** — we refuse any document carrying a ``<!DOCTYPE>`` (a
  GetCapabilities response never needs one), so no internal/external entities are ever
  expanded. Combined with a response **size cap**, this blocks billion-laughs and external-
  entity attacks while using only the stdlib (no defusedxml dependency).
- **Scheme allowlist** — only ``http``/``https`` URLs are fetched (so a ``WFS:file:///…``
  trick can't read local files); HTTPS certificates are validated by urllib's defaults.
- **Timeouts** — every request has a bounded timeout; no credentials are sent or stored
  (public services only — authenticated OWS is out of scope for now).
- The URL is user-supplied on the command line (like ``curl``); this is intended, not SSRF.
"""

from __future__ import annotations

import urllib.parse
import urllib.request

_TIMEOUT = 30  # seconds
_MAX_BYTES = 25_000_000  # cap a GetCapabilities response (real ones are KBs–low MBs)
_SERVICE_PREFIXES = ("wfs:", "wms:")
_SCHEME_PREFIXES = ("http://", "https://")


def is_service_url(token: str) -> bool:
    """True if ``token`` looks like a remote OWS endpoint `show` should query — an
    ``http(s)://`` URL or a GDAL-style ``WFS:``/``WMS:`` prefix."""
    low = token.lower()
    return low.startswith(_SCHEME_PREFIXES) or low.startswith(_SERVICE_PREFIXES)


def _split_prefix(url: str):
    """Return ``(service|None, base_url)`` — peeling a ``WFS:``/``WMS:`` scheme prefix."""
    low = url.lower()
    if low.startswith("wfs:"):
        return "WFS", url[4:]
    if low.startswith("wms:"):
        return "WMS", url[4:]
    return None, url


def _detect_service(url: str):
    """Return ``(service, base_url)``. The service comes from (in order): a ``WFS:``/``WMS:``
    prefix; an explicit ``service=`` query parameter; or the path (``…/wfs``, ``…/wms``).
    ``service`` is ``None`` when undeterminable — the caller then asks the user to specify."""
    service, base = _split_prefix(url)
    parts = urllib.parse.urlsplit(base)
    if service is None:
        for key, val in urllib.parse.parse_qsl(parts.query):
            if key.lower() == "service" and val.upper() in ("WFS", "WMS"):
                service = val.upper()
                break
    if service is None:
        path = parts.path.lower()
        if "wfs" in path:
            service = "WFS"
        elif "wms" in path:
            service = "WMS"
    return service, base


def _capabilities_url(base: str, service: str) -> str:
    """Build a GetCapabilities URL: keep the endpoint and any non-OWS query params, then set
    ``service``/``request``/``version`` for the chosen service."""
    parts = urllib.parse.urlsplit(base)
    if parts.scheme not in ("http", "https"):
        raise ValueError(f"unsupported URL scheme `{parts.scheme}` — only http/https")
    keep = [(k, v) for k, v in urllib.parse.parse_qsl(parts.query)
            if k.lower() not in ("service", "request", "version")]
    keep.append(("service", service))
    keep.append(("request", "GetCapabilities"))
    keep.append(("version", "2.0.0" if service == "WFS" else "1.3.0"))
    return urllib.parse.urlunsplit(
        (parts.scheme, parts.netloc, parts.path, urllib.parse.urlencode(keep), ""))


def _http_get(url: str) -> bytes:
    """Fetch ``url`` (http/https only), capped and timed. The caller has already built a
    GetCapabilities URL via :func:`_capabilities_url`, which validates the scheme."""
    try:
        from . import __version__

        ua = f"niva/{__version__} (+https://github.com/johnzastrow/niva)"
    except Exception:  # noqa: BLE001
        ua = "niva"
    req = urllib.request.Request(url, headers={"User-Agent": ua})
    with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:  # noqa: S310 — scheme checked
        data = resp.read(_MAX_BYTES + 1)
    if len(data) > _MAX_BYTES:
        raise ValueError(f"capabilities response exceeded {_MAX_BYTES} bytes")
    return data


def _safe_xml(data: bytes):
    """Parse capabilities XML, refusing any DOCTYPE (so no entity expansion is possible)."""
    import xml.etree.ElementTree as ET

    if b"<!DOCTYPE" in data[:16384] or b"<!doctype" in data[:16384]:
        raise ValueError("refusing to parse XML with a DOCTYPE declaration (possible XXE)")
    return ET.fromstring(data)


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _child_text(elem, name: str):
    for c in elem:
        if _local(c.tag) == name and c.text and c.text.strip():
            return c.text.strip()
    return None


def _parse_wfs(root, base: str) -> list:
    """WFS GetCapabilities → one entry per ``FeatureType`` (name + default CRS)."""
    entries = []
    for ft in (e for e in root.iter() if _local(e.tag) == "FeatureType"):
        name = _child_text(ft, "Name")
        if not name:
            continue
        crs = _child_text(ft, "DefaultCRS") or _child_text(ft, "DefaultSRS") or ""
        entries.append({"name": name, "kind": "vector", "type": crs or "feature type",
                        "format": "WFS", "ref": f"WFS:{base}"})
    return entries


def _parse_wms(root, base: str) -> list:
    """WMS GetCapabilities → one entry per *named* ``Layer`` (unnamed container Layers, which
    only group others, are skipped). Deduplicated by name, order preserved."""
    entries, seen = [], set()
    for lyr in (e for e in root.iter() if _local(e.tag) == "Layer"):
        name = _child_text(lyr, "Name")  # only direct Name ⇒ requestable layer
        if not name or name in seen:
            continue
        seen.add(name)
        title = _child_text(lyr, "Title") or ""
        entries.append({"name": name, "kind": "raster", "type": title or "WMS layer",
                        "format": "WMS", "ref": f"WMS:{base}"})
    return entries


def list_service(url: str, *, fetch=None) -> list:
    """List the layers/feature types at a remote OWS endpoint. ``fetch`` (for tests) is a
    ``callable(capabilities_url) -> bytes``; the default fetches over HTTP. Returns the same
    entry dicts as the other `show` sources: ``{name, kind, type, format, ref}``."""
    fetch = fetch or _http_get
    service, base = _detect_service(url)
    if service is None:
        raise ValueError(
            "could not tell whether this is a WFS or WMS endpoint — add `?service=WFS` or "
            "`?service=WMS` to the URL (or a `WFS:`/`WMS:` prefix)")
    data = fetch(_capabilities_url(base, service))
    root = _safe_xml(data)
    return _parse_wfs(root, base) if service == "WFS" else _parse_wms(root, base)
