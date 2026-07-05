"""Remote service listing for the `show` verb — WFS feature types, WMS layers, ArcGIS REST
layers/tables, and XYZ tile templates.

This is pure standard library (HTTP + XML + JSON, no QGIS, no third-party deps), so it is
fully unit-testable offline by injecting a ``fetch`` callable. The backend (`PyqgisBackend`)
just delegates here; the engine routes a service URL to ``Backend.list_service``.

Security (per the project's secure-coding baseline):
- **XXE / entity-expansion** — we refuse any XML carrying a ``<!DOCTYPE>`` (a GetCapabilities
  response never needs one), so no internal/external entities are ever expanded. Combined with
  a response **size cap**, this blocks billion-laughs and external-entity attacks while using
  only the stdlib (no defusedxml dependency). ArcGIS REST is JSON (``json.loads`` — no entity
  risk).
- **Scheme allowlist** — only ``http``/``https`` URLs are fetched (so a ``WFS:file:///…``
  trick can't read local files); HTTPS certificates are validated by urllib's defaults.
- **Timeouts** — every request has a bounded timeout; no credentials are sent or stored
  (public services only — authenticated services are out of scope for now).
- The URL is user-supplied on the command line (like ``curl``); this is intended, not SSRF.
"""

from __future__ import annotations

import re
import urllib.parse
import urllib.request

_TIMEOUT = 30  # seconds
_MAX_BYTES = 25_000_000  # cap a capabilities/JSON response (real ones are KBs–low MBs)
_SERVICE_PREFIXES = ("wfs:", "wms:")
_SCHEME_PREFIXES = ("http://", "https://")
# An ArcGIS REST service endpoint (optionally a single layer with a trailing /<id>).
_ARCGIS_RE = re.compile(r"/(feature|map|image)server(/\d+)?/?$", re.IGNORECASE)
# ESRI geometry type → a familiar geometry name.
_ESRI_GEOM = {
    "esriGeometryPoint": "Point", "esriGeometryMultipoint": "MultiPoint",
    "esriGeometryPolyline": "LineString", "esriGeometryPolygon": "Polygon",
    "esriGeometryEnvelope": "Envelope",
}


def is_service_url(token: str) -> bool:
    """True if ``token`` looks like a remote endpoint `show` should query — an ``http(s)://``
    URL (WFS/WMS/ArcGIS REST/XYZ) or a GDAL-style ``WFS:``/``WMS:`` prefix."""
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
    """Return ``(service, base_url)`` where service is ``WFS``/``WMS``/``ARCGIS``/``XYZ`` or
    ``None``. Determined (in order) by: a ``WFS:``/``WMS:`` prefix; an XYZ ``{z}/{x}/{y}``
    template; an ArcGIS REST path (``/rest/services/`` or ``…/FeatureServer``); an explicit
    ``service=WFS|WMS`` query parameter; or a ``…/wfs``/``…/wms`` path. ``None`` when it can't
    be told — the caller then asks the user to specify."""
    service, base = _split_prefix(url)
    if service is not None:
        return service, base
    # XYZ tile template — the URL *is* the layer; no capabilities to fetch.
    if ("{x}" in base and "{y}" in base) or "{q}" in base:
        return "XYZ", base
    parts = urllib.parse.urlsplit(base)
    path = parts.path.lower()
    if "/rest/services/" in path or _ARCGIS_RE.search(path):
        return "ARCGIS", base
    for key, val in urllib.parse.parse_qsl(parts.query):
        if key.lower() == "service" and val.upper() in ("WFS", "WMS"):
            return val.upper(), base
    if "wfs" in path:
        return "WFS", base
    if "wms" in path:
        return "WMS", base
    return None, base


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
    # Hard scheme allowlist: only http/https ever reach the network — never file:, ftp:,
    # data:, or a custom scheme (defence against SSRF / local-file reads).
    scheme = urllib.parse.urlsplit(url).scheme.lower()
    if scheme not in ("http", "https"):
        raise ValueError(f"refusing non-http(s) URL scheme: {scheme!r}")
    req = urllib.request.Request(url, headers={"User-Agent": ua})
    # Build an opener with ONLY http/https handlers (no FileHandler/FTPHandler). This blocks
    # the initial request AND any redirect from reaching file:/ftp: — a redirect to
    # file:///etc/passwd finds no handler and errors instead of reading a local file. Using
    # OpenerDirector.open (not urllib.request.urlopen) also keeps the default file/ftp
    # handlers out of the picture entirely.
    opener = urllib.request.OpenerDirector()
    opener.add_handler(urllib.request.HTTPHandler())
    opener.add_handler(urllib.request.HTTPSHandler())
    opener.add_handler(urllib.request.HTTPRedirectHandler())
    opener.add_handler(urllib.request.HTTPErrorProcessor())
    with opener.open(req, timeout=_TIMEOUT) as resp:
        data = resp.read(_MAX_BYTES + 1)
    if len(data) > _MAX_BYTES:
        raise ValueError(f"capabilities response exceeded {_MAX_BYTES} bytes")
    return data


def _safe_xml(data: bytes):
    """Parse capabilities XML **safely**: reject any DOCTYPE up front, so there are no entities
    to expand — this neutralises XXE and billion-laughs before the parser ever runs. stdlib
    ``xml.etree`` is otherwise fine for entity-free XML; the ``# nosec`` markers acknowledge
    Bandit's blanket B405/B314 (it can't see the DOCTYPE guard). We avoid a ``defusedxml``
    dependency to keep the vendored package zero-dependency (see the security-scanning notes in
    docs/guide/qgis-plugin-publishing.md)."""
    import xml.etree.ElementTree as ET  # nosec B405 — DOCTYPE refused below; no entity expansion

    if b"<!DOCTYPE" in data[:16384] or b"<!doctype" in data[:16384]:
        raise ValueError("refusing to parse XML with a DOCTYPE declaration (possible XXE)")
    return ET.fromstring(data)  # nosec B314 — input validated DOCTYPE-free above


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


def _arcgis_json_url(base: str) -> str:
    """The ``?f=json`` form of an ArcGIS REST service/layer URL (http/https only)."""
    parts = urllib.parse.urlsplit(base)
    if parts.scheme not in ("http", "https"):
        raise ValueError(f"unsupported URL scheme `{parts.scheme}` — only http/https")
    query = [(k, v) for k, v in urllib.parse.parse_qsl(parts.query) if k.lower() != "f"]
    query.append(("f", "json"))
    return urllib.parse.urlunsplit(
        (parts.scheme, parts.netloc, parts.path, urllib.parse.urlencode(query), ""))


def _arcgis_entry(d: dict, base: str, *, table: bool, single: bool) -> dict:
    lid = d.get("id")
    name = str(d.get("name") or (f"layer {lid}" if lid is not None else "?"))
    geom = _ESRI_GEOM.get(d.get("geometryType"))
    if table or (geom is None and d.get("type") == "Table"):
        kind, typ = "table", "(table)"
    else:
        kind, typ = "vector", (geom or "layer")
    ref = base.rstrip("/") if single else f"{base.rstrip('/')}/{lid}"
    return {"name": name, "kind": kind, "type": typ, "format": "ArcGIS", "ref": ref}


def _parse_arcgis(data: bytes, base: str) -> list:
    """ArcGIS REST ``f=json`` → one entry per layer/table. A service root has ``layers``
    (and ``tables``); a single ``…/FeatureServer/0`` endpoint is its own metadata object."""
    import json

    try:
        obj = json.loads(data)
    except ValueError as exc:
        raise ValueError(f"invalid ArcGIS REST JSON: {exc}") from exc
    if isinstance(obj, dict) and obj.get("error"):
        raise ValueError(f"ArcGIS REST error: {(obj['error'] or {}).get('message', '?')}")
    if not isinstance(obj, dict):
        raise ValueError("unexpected ArcGIS REST response")

    layers, tables = obj.get("layers"), obj.get("tables")
    if layers or tables:
        entries = [_arcgis_entry(d, base, table=False, single=False) for d in (layers or [])]
        entries += [_arcgis_entry(d, base, table=True, single=False) for d in (tables or [])]
        return entries
    if obj.get("name") or obj.get("id") is not None:  # a single layer/table endpoint
        return [_arcgis_entry(obj, base, table=obj.get("type") == "Table", single=True)]
    return []


def _parse_xyz(url: str) -> list:
    """An XYZ tile template is a single (raster) layer — echo it as one loadable entry."""
    parts = urllib.parse.urlsplit(url)
    name = parts.netloc or url
    return [{"name": name, "kind": "raster", "type": "XYZ tiles", "format": "XYZ",
             "ref": f"type=xyz&url={url}"}]


def list_service(url: str, *, fetch=None) -> list:
    """List the layers at a remote endpoint — WFS feature types, WMS layers, ArcGIS REST
    layers/tables, or an XYZ tile template. ``fetch`` (for tests) is a
    ``callable(url) -> bytes``; the default fetches over HTTP. Returns the same entry dicts
    as the other `show` sources: ``{name, kind, type, format, ref}``."""
    fetch = fetch or _http_get
    service, base = _detect_service(url)
    if service == "XYZ":
        return _parse_xyz(base)  # no network — the template is the layer
    if service is None:
        raise ValueError(
            "could not tell what kind of service this is — add `?service=WFS`/`?service=WMS` "
            "(or a `WFS:`/`WMS:` prefix), pass an ArcGIS REST `…/FeatureServer` URL, or an XYZ "
            "`{z}/{x}/{y}` template")
    if service == "ARCGIS":
        return _parse_arcgis(fetch(_arcgis_json_url(base)), base)
    data = fetch(_capabilities_url(base, service))
    root = _safe_xml(data)
    return _parse_wfs(root, base) if service == "WFS" else _parse_wms(root, base)
