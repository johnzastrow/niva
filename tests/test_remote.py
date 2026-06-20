"""Remote OWS listing (`niva.remote`) — the WFS/WMS backing for `show`.

Pure standard library: no QGIS and no network — the GetCapabilities fetch is injected, so
every parse/detect/security path is exercised offline against canned capabilities documents.
A live, network-touching smoke test is gated behind ``NIVA_TEST_REMOTE=1``.
"""

import os
import unittest

from niva import remote

WFS20 = b"""<?xml version="1.0"?>
<wfs:WFS_Capabilities xmlns:wfs="http://www.opengis.net/wfs/2.0" version="2.0.0">
  <wfs:FeatureTypeList>
    <wfs:FeatureType>
      <wfs:Name>topp:states</wfs:Name>
      <wfs:Title>USA States</wfs:Title>
      <wfs:DefaultCRS>urn:ogc:def:crs:EPSG::4326</wfs:DefaultCRS>
    </wfs:FeatureType>
    <wfs:FeatureType>
      <wfs:Name>topp:roads</wfs:Name>
      <wfs:DefaultCRS>EPSG:3857</wfs:DefaultCRS>
    </wfs:FeatureType>
  </wfs:FeatureTypeList>
</wfs:WFS_Capabilities>"""

WFS11 = b"""<?xml version="1.0"?>
<wfs:WFS_Capabilities xmlns:wfs="http://www.opengis.net/wfs" version="1.1.0">
  <wfs:FeatureTypeList>
    <wfs:FeatureType>
      <wfs:Name>ns:rivers</wfs:Name>
      <wfs:DefaultSRS>EPSG:4258</wfs:DefaultSRS>
    </wfs:FeatureType>
  </wfs:FeatureTypeList>
</wfs:WFS_Capabilities>"""

WMS13 = b"""<?xml version="1.0"?>
<WMS_Capabilities xmlns="http://www.opengis.net/wms" version="1.3.0">
 <Capability>
  <Layer>
    <Title>Root container (no Name - skipped)</Title>
    <Layer queryable="1">
      <Name>osm</Name><Title>OpenStreetMap</Title><CRS>EPSG:3857</CRS>
    </Layer>
    <Layer>
      <Name>topo</Name><Title>Topographic</Title>
    </Layer>
    <Layer>
      <Name>osm</Name><Title>Duplicate name - deduped</Title>
    </Layer>
  </Layer>
 </Capability>
</WMS_Capabilities>"""


class TestServiceDetection(unittest.TestCase):
    def test_is_service_url(self):
        for ok in ("http://x/wfs", "https://x/wms", "WFS:http://x", "wms:http://x"):
            self.assertTrue(remote.is_service_url(ok), ok)
        for no in ("data.gpkg", "/tmp/x", "@pg.table", "ftp://x"):
            self.assertFalse(remote.is_service_url(no), no)

    def test_detect_from_query_param(self):
        self.assertEqual(remote._detect_service("https://h/ows?service=WFS")[0], "WFS")
        self.assertEqual(remote._detect_service("https://h/ows?SERVICE=wms")[0], "WMS")

    def test_detect_from_prefix(self):
        svc, base = remote._detect_service("WFS:https://h/x")
        self.assertEqual(svc, "WFS")
        self.assertEqual(base, "https://h/x")

    def test_detect_from_path(self):
        self.assertEqual(remote._detect_service("https://h/geoserver/wfs")[0], "WFS")
        self.assertEqual(remote._detect_service("https://h/geoserver/wms")[0], "WMS")

    def test_undeterminable_is_none(self):
        self.assertIsNone(remote._detect_service("https://h/endpoint")[0])


class TestCapabilitiesUrl(unittest.TestCase):
    def test_sets_service_request_version(self):
        u = remote._capabilities_url("https://h/ows", "WFS")
        self.assertIn("service=WFS", u)
        self.assertIn("request=GetCapabilities", u)
        self.assertIn("version=2.0.0", u)

    def test_wms_version(self):
        self.assertIn("version=1.3.0", remote._capabilities_url("https://h/ows", "WMS"))

    def test_preserves_other_params_replaces_ows_ones(self):
        u = remote._capabilities_url("https://h/ows?map=/x.map&service=WMS&request=GetMap", "WFS")
        self.assertIn("map=%2Fx.map", u)
        self.assertIn("service=WFS", u)
        self.assertNotIn("GetMap", u)

    def test_non_http_scheme_rejected(self):
        with self.assertRaises(ValueError):
            remote._capabilities_url("file:///etc/passwd", "WFS")


class TestParsing(unittest.TestCase):
    def test_parse_wfs_20(self):
        rows = remote.list_service("https://h/wfs?service=WFS", fetch=lambda u: WFS20)
        self.assertEqual([r["name"] for r in rows], ["topp:states", "topp:roads"])
        self.assertTrue(all(r["kind"] == "vector" and r["format"] == "WFS" for r in rows))
        self.assertIn("4326", rows[0]["type"])
        self.assertTrue(rows[0]["ref"].startswith("WFS:"))

    def test_parse_wfs_11_default_srs(self):
        rows = remote.list_service("WFS:https://h/wfs", fetch=lambda u: WFS11)
        self.assertEqual(rows[0]["name"], "ns:rivers")
        self.assertEqual(rows[0]["type"], "EPSG:4258")

    def test_parse_wms_named_layers_only_and_deduped(self):
        rows = remote.list_service("https://h/wms?service=WMS", fetch=lambda u: WMS13)
        names = [r["name"] for r in rows]
        self.assertEqual(names, ["osm", "topo"])  # container skipped, duplicate deduped
        self.assertTrue(all(r["kind"] == "raster" and r["format"] == "WMS" for r in rows))
        self.assertEqual(rows[0]["type"], "OpenStreetMap")

    def test_fetch_receives_a_getcapabilities_url(self):
        seen = {}

        def fetch(u):
            seen["url"] = u
            return WFS20

        remote.list_service("https://h/wfs?service=WFS", fetch=fetch)
        self.assertIn("request=GetCapabilities", seen["url"])


class TestSecurity(unittest.TestCase):
    def test_doctype_is_refused(self):
        evil = (b'<?xml version="1.0"?>\n<!DOCTYPE x [<!ENTITY a "boom">]>\n'
                b'<wfs:WFS_Capabilities xmlns:wfs="http://www.opengis.net/wfs/2.0"/>')
        with self.assertRaises(ValueError):
            remote.list_service("https://h/wfs?service=WFS", fetch=lambda u: evil)

    def test_undeterminable_service_raises(self):
        with self.assertRaises(ValueError):
            remote.list_service("https://h/endpoint", fetch=lambda u: WFS20)


@unittest.skipUnless(os.environ.get("NIVA_TEST_REMOTE") == "1",
                     "set NIVA_TEST_REMOTE=1 to hit the network")
class TestLiveOws(unittest.TestCase):
    def test_live_wfs(self):
        rows = remote.list_service("https://demo.mapserver.org/cgi-bin/wfs?service=WFS")
        self.assertTrue(rows)
        self.assertTrue(all(r["format"] == "WFS" for r in rows))

    def test_live_wms(self):
        rows = remote.list_service("https://ows.terrestris.de/osm/service?service=WMS")
        self.assertTrue(any(r["name"] == "OSM-WMS" for r in rows))


if __name__ == "__main__":
    unittest.main()
