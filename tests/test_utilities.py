"""Tests for the utility verbs: notify (ntfy), email, catalog. No QGIS, no network —
network calls are monkeypatched; catalog runs over a MockBackend and a temp tree."""

import os
import tempfile
import unittest

from niva import flow
from niva.engine import MockBackend
from niva.errors import FlowError
from niva import utilities


class TestNotify(unittest.TestCase):
    def test_send_ntfy_posts_to_resolved_url(self):
        captured = {}

        def fake_send(message, **kw):
            captured["message"] = message
            captured.update(kw)
            return "https://ntfy.sh/mytopic"

        orig = utilities.send_ntfy
        utilities.send_ntfy = fake_send
        try:
            flow('notify "all done" to=mytopic title=niva', backend=MockBackend())
        finally:
            utilities.send_ntfy = orig
        self.assertEqual(captured["message"], "all done")
        self.assertEqual(captured["topic"], "mytopic")
        self.assertEqual(captured["title"], "niva")

    def test_notify_requires_message(self):
        with self.assertRaises(FlowError):
            flow("notify to=x", backend=MockBackend())

    def test_send_ntfy_requires_topic(self):
        # no topic arg and no NIVA_NTFY_TOPIC in this (empty) env
        with self.assertRaises(FlowError):
            utilities.send_ntfy("hi", env={})

    def test_notify_is_pass_through(self):
        # notify returns the upstream layer so the flow can continue
        orig = utilities.send_ntfy
        utilities.send_ntfy = lambda *a, **k: "url"
        try:
            # load → notify → save: save must still receive the loaded layer
            mb = MockBackend()
            flow('load a.gpkg | notify "x" to=t | save out.gpkg', backend=mb)
            self.assertIn(("save", "out.gpkg"), mb.calls)
        finally:
            utilities.send_ntfy = orig


class TestEmail(unittest.TestCase):
    def test_send_email_requires_smtp_host(self):
        with self.assertRaises(FlowError):
            utilities.send_email(to="a@b.com", env={})

    def test_send_email_requires_recipient(self):
        with self.assertRaises(FlowError):
            utilities.send_email(to="", env={"NIVA_SMTP_HOST": "smtp.example.com"})

    def test_gmail_sender_infers_gmail_smtp(self):
        # A @gmail.com sender with no explicit host should resolve to Gmail's SMTP.
        sent = {}

        class FakeSMTP:
            def __init__(self, host, port, timeout=0):
                sent["host"], sent["port"] = host, port

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def starttls(self, context=None):
                sent["starttls"] = True

            def login(self, u, p):
                sent["login"] = u

            def send_message(self, msg):
                sent["to"] = msg["To"]

        import smtplib

        orig = smtplib.SMTP
        smtplib.SMTP = FakeSMTP
        try:
            utilities.send_email(
                to="dest@example.com",
                subject="hi",
                env={
                    "NIVA_SMTP_FROM": "me@gmail.com",
                    "NIVA_SMTP_USER": "me@gmail.com",
                    "NIVA_SMTP_PASSWORD": "app-password",
                },
            )
        finally:
            smtplib.SMTP = orig
        self.assertEqual(sent["host"], "smtp.gmail.com")
        self.assertEqual(sent["port"], 587)
        self.assertTrue(sent["starttls"])  # TLS enforced
        self.assertEqual(sent["to"], "dest@example.com")

    def test_email_verb_passes_options_through(self):
        captured = {}

        def fake(**kw):
            captured.update(kw)
            return kw["to"]

        orig = utilities.send_email
        utilities.send_email = fake
        try:
            flow(
                'email to=me@example.com subject="done" body="ok"',
                backend=MockBackend(),
            )
        finally:
            utilities.send_email = orig
        self.assertEqual(captured["to"], "me@example.com")
        self.assertEqual(captured["subject"], "done")


class TestCatalog(unittest.TestCase):
    def test_catalog_recurses_and_writes_report(self):
        root = tempfile.mkdtemp(prefix="niva_cat_")
        # a couple of geospatial files (empty — MockBackend doesn't read them) and a
        # non-geospatial file that must be ignored
        os.makedirs(os.path.join(root, "sub"))
        open(os.path.join(root, "a.gpkg"), "w").close()
        open(os.path.join(root, "sub", "b.tif"), "w").close()
        open(os.path.join(root, "notes.txt"), "w").close()

        out = os.path.join(root, "catalog.md")
        flow(f'catalog "{root}"', backend=MockBackend())
        self.assertTrue(os.path.exists(out))
        report = open(out).read()
        self.assertIn("Geospatial data catalog", report)
        self.assertIn("a.gpkg", report)
        self.assertIn(os.path.join("sub", "b.tif"), report)
        self.assertNotIn("notes.txt", report)  # non-geospatial ignored

    def test_catalog_requires_a_directory(self):
        with self.assertRaises(FlowError):
            flow("catalog /no/such/dir/here", backend=MockBackend())

    def test_catalog_custom_output_path(self):
        root = tempfile.mkdtemp(prefix="niva_cat_")
        open(os.path.join(root, "a.gpkg"), "w").close()
        out = os.path.join(root, "report.md")
        flow(f'catalog "{root}" to="{out}"', backend=MockBackend())
        self.assertTrue(os.path.exists(out))

    def test_catalog_deep_reports_quality_and_reaches_profiler(self):
        root = tempfile.mkdtemp(prefix="niva_cat_")
        open(os.path.join(root, "a.gpkg"), "w").close()
        out = os.path.join(root, "cat.md")
        mb = MockBackend()
        flow(f'catalog "{root}" deep to="{out}"', backend=mb)
        report = open(out).read()
        self.assertIn("quality:", report)  # deep profiling rendered
        # deep=True actually reached the profiler (MockBackend logs ("assess", name, deep))
        self.assertTrue(any(c[0] == "assess" and c[2] is True for c in mb.calls))

    def test_catalog_shallow_omits_quality(self):
        root = tempfile.mkdtemp(prefix="niva_cat_")
        open(os.path.join(root, "a.gpkg"), "w").close()
        out = os.path.join(root, "cat.md")
        flow(f'catalog "{root}" to="{out}"', backend=MockBackend())
        self.assertNotIn("quality:", open(out).read())

    def test_catalog_database_source(self):
        # catalog accepts an @conn database like `show` does, loading each table by name.
        out = os.path.join(tempfile.mkdtemp(prefix="niva_cat_"), "db.md")
        mb = MockBackend()
        flow(f'catalog @pg to="{out}"', backend=mb)
        report = open(out).read()
        self.assertIn("roads", report)
        self.assertIn("homes", report)
        self.assertTrue(any(c[0] == "load_table" for c in mb.calls))  # not plain load

    def test_catalog_service_source(self):
        # catalog accepts a remote OWS service URL like `show` does.
        out = os.path.join(tempfile.mkdtemp(prefix="niva_cat_"), "svc.md")
        mb = MockBackend()
        flow(f'catalog "https://example.com/wfs" to="{out}"', backend=mb)
        self.assertIn("topp:states", open(out).read())
        self.assertTrue(any(c[0] == "list_service" for c in mb.calls))

    def test_catalog_unknown_option_rejected(self):
        with self.assertRaises(FlowError):
            flow("catalog /tmp bogus=1", backend=MockBackend())


class TestShowFormat(unittest.TestCase):
    """`format_show` — the Markdown table the `show` verb renders."""

    def _entry(self, name, kind="vector", typ="Polygon", fmt="GPKG", ref=None):
        return {
            "name": name,
            "kind": kind,
            "type": typ,
            "format": fmt,
            "ref": ref or f"x.gpkg|layername={name}",
        }

    def test_table_has_header_and_rows(self):
        from niva.utilities import format_show

        out = format_show("x.gpkg", [self._entry("roads"), self._entry("rivers")])
        self.assertIn("| Layer | Kind | Type | Format | Source", out)
        self.assertIn("| roads | vector | Polygon | GPKG |", out)
        self.assertIn("2 datasets.", out)

    def test_singular_vs_plural_and_db_noun(self):
        from niva.utilities import format_show

        self.assertIn("1 dataset.", format_show("x", [self._entry("a")]))
        self.assertIn("1 table.", format_show("@c", [self._entry("a")], is_db=True))
        self.assertIn(
            "2 tables.",
            format_show("@c", [self._entry("a"), self._entry("b")], is_db=True),
        )

    def test_empty_listing(self):
        from niva.utilities import format_show

        out = format_show("x", [])
        self.assertIn("0 datasets.", out)
        self.assertIn("No loadable layers", out)

    def test_db_footer_vs_file_footer(self):
        from niva.utilities import format_show

        self.assertIn("ogrinfo", format_show("x", [self._entry("a")]))
        self.assertIn(
            "credentials stay in QGIS",
            format_show("@c", [self._entry("a")], is_db=True),
        )

    def test_examples_use_the_first_real_source(self):
        from niva.utilities import format_show

        out = format_show(
            "x.gpkg", [self._entry("roads", ref="x.gpkg|layername=roads")]
        )
        self.assertIn("Examples", out)
        # shell-ready: wrapped in `niva '…'` so a paste into bash doesn't eat the quotes or
        # split on `|` (the reported failure)
        # …and the buffer example reprojects FIRST, so `100m` is valid even on a geographic
        # (degrees) layer — otherwise `buffer 100m` errors on EPSG:4326 data.
        self.assertIn(
            'niva \'load "x.gpkg|layername=roads" | reproject EPSG:3857 | buffer 100m '
            "| save ~/buffered.gpkg'",
            out,
        )
        # second example is `fixgeom` (geometry-agnostic) — `centroid` crashed on mixed geometry
        self.assertIn("| fixgeom | save ~/fixed.gpkg", out)
        self.assertNotIn("| centroid ", out)

    def test_examples_include_write_into_existing_targets(self):
        from niva.utilities import format_show

        out = format_show(
            "x.gpkg", [self._entry("roads", ref="x.gpkg|layername=roads")]
        )
        self.assertIn("Write into an **existing** container", out)
        self.assertIn("| save ~/analysis.gpkg as roads", out)  # add a layer to a gpkg
        self.assertIn(
            "| save @conn.public.roads mode=append", out
        )  # append to a DB table

    def test_write_example_sanitises_a_problematic_name(self):
        from niva.utilities import format_show

        out = format_show(
            "@c",
            [self._entry("My Roads #1", fmt="postgres", ref="@c.public.My Roads #1")],
            is_db=True,
        )
        # the layer/table name in the save target is a clean identifier, no quoting needed
        self.assertIn("| save ~/analysis.gpkg as my_roads_1", out)
        self.assertIn("| save @conn.public.my_roads_1 mode=append", out)

    def test_examples_pick_raster_aliases_for_a_raster(self):
        from niva.utilities import format_show

        out = format_show(
            "dem.tif",
            [
                self._entry(
                    "dem", kind="raster", typ="1 band", fmt="GTiff", ref="dem.tif"
                )
            ],
        )
        self.assertIn(
            "niva 'load dem.tif | warp EPSG:3857", out
        )  # warp first (always safe)
        self.assertIn("| hillshade | save ~/hillshade.tif", out)

    def test_aspatial_example_is_runnable(self):
        # `assess` has no stdout form — its example MUST name a `to` output, else copying it
        # yields a flow that errors. Regression guard for the broken `… | assess` example.
        from niva.utilities import format_show

        out = format_show(
            "stats.gpkg",
            [self._entry("stats", kind="table", typ="(aspatial)", ref="stats.gpkg")],
        )
        self.assertIn("load stats.gpkg | assess to ", out)
        self.assertNotIn("| assess\n", out)  # never a bare, output-less assess

    def test_service_listing_has_no_load_examples(self):
        from niva.utilities import format_show

        out = format_show(
            "https://h/wfs",
            [self._entry("roads", fmt="WFS", ref="WFS:https://h/wfs")],
            is_service=True,
        )
        self.assertNotIn("Examples", out)  # remote sources aren't `load`-piped

    def test_example_quotes_a_source_with_special_chars(self):
        # a ref with `#` (comment), a space, or `|` must be quoted in the example, else the
        # flow truncates/splits — real PostGIS table names like `name-with-dash#hash`/`My Roads`.
        from niva.utilities import format_show

        for ref in ("@c.public.name-with-dash#hash", "@c.public.My Roads"):
            out = format_show(
                "@c", [self._entry("t", fmt="postgres", ref=ref)], is_db=True
            )
            self.assertIn(f'niva \'load "{ref}" |', out, ref)
        # a plain ref needs no quoting
        plain = format_show(
            "@c", [self._entry("t", fmt="postgres", ref="@c.public.roads")], is_db=True
        )
        self.assertIn("niva 'load @c.public.roads |", plain)


class TestShow(unittest.TestCase):
    """The `show` verb over MockBackend (the live listing is in tests/test_pyqgis.py).
    MockBackend records every call; with ``layer_map`` set, only mapped files report
    layers, so a directory scan that probes every file mirrors real querySublayers."""

    def _run(self, flowtext, backend):
        import contextlib
        import io

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            flow(flowtext, backend=backend)
        return buf.getvalue()

    def _called_paths(self, backend):
        return [c[1] for c in backend.calls if c[0] == "list_layers"]

    # --- a single file -------------------------------------------------------

    def test_show_a_file_lists_layers(self):
        root = tempfile.mkdtemp(prefix="niva_show_")
        gpkg = os.path.join(root, "data.gpkg")
        open(gpkg, "w").close()
        backend = MockBackend()
        out = self._run(f'show "{gpkg}"', backend)
        self.assertIn(("list_layers", gpkg), backend.calls)
        self.assertIn("Data at", out)
        self.assertIn("layer_a", out)
        self.assertIn("layername=layer_a", out)  # copy-pasteable source

    # --- directories: shallow vs deep ---------------------------------------

    def _tree(self):
        """root/a.gpkg, root/data.sqlite, root/notes.txt, root/sub/b.gpkg."""
        root = tempfile.mkdtemp(prefix="niva_show_")
        os.makedirs(os.path.join(root, "sub"))
        for rel in (
            "a.gpkg",
            "data.sqlite",
            "notes.txt",
            os.path.join("sub", "b.gpkg"),
        ):
            open(os.path.join(root, rel), "w").close()
        a = os.path.join(root, "a.gpkg")
        sqlite = os.path.join(root, "data.sqlite")
        b = os.path.join(root, "sub", "b.gpkg")
        backend = MockBackend()
        backend.layer_map = {a: ["ra"], sqlite: ["rs1", "rs2"], b: ["rb"]}
        return root, backend, a, sqlite, b

    def test_shallow_lists_immediate_children_any_format(self):
        root, backend, a, sqlite, b = self._tree()
        out = self._run(f'show "{root}"', backend)
        called = self._called_paths(backend)
        # .sqlite is probed (no allowlist), .txt is skipped, sub/ is not descended.
        self.assertIn(a, called)
        self.assertIn(sqlite, called)
        self.assertNotIn(b, called)
        self.assertTrue(all("notes.txt" not in p for p in called))
        self.assertIn("rs1", out)  # SQLite layer surfaced
        self.assertNotIn("rb", out)  # nested layer NOT in a shallow listing

    def test_deep_recurses_into_subdirectories(self):
        root, backend, a, sqlite, b = self._tree()
        out = self._run(f'show "{root}" deep', backend)
        called = self._called_paths(backend)
        self.assertIn(b, called)  # nested container now probed
        self.assertIn("rb", out)

    def test_recursive_is_an_alias_for_deep(self):
        root, backend, a, sqlite, b = self._tree()
        self._run(f'show "{root}" recursive', backend)
        self.assertIn(b, self._called_paths(backend))

    def test_sidecar_files_are_skipped(self):
        root = tempfile.mkdtemp(prefix="niva_show_")
        for fn in (
            "roads.shp",
            "roads.dbf",
            "roads.shx",
            "roads.prj",
            "dem.tif.aux.xml",
        ):
            open(os.path.join(root, fn), "w").close()
        backend = MockBackend()
        backend.layer_map = {os.path.join(root, "roads.shp"): ["roads"]}
        self._run(f'show "{root}"', backend)
        called = self._called_paths(backend)
        self.assertIn(os.path.join(root, "roads.shp"), called)
        for sidecar in ("roads.dbf", "roads.shx", "roads.prj", "dem.tif.aux.xml"):
            self.assertTrue(
                all(not p.endswith(sidecar) for p in called),
                f"{sidecar} should be skipped",
            )

    def test_directory_dataset_is_a_container_not_descended(self):
        root = tempfile.mkdtemp(prefix="niva_show_")
        gdb = os.path.join(root, "archive.gdb")
        os.makedirs(gdb)
        inner = os.path.join(gdb, "a00000001.gdbtable")
        open(inner, "w").close()
        backend = MockBackend()
        backend.layer_map = {gdb: ["feature_class_1"]}
        out = self._run(f'show "{root}"', backend)
        called = self._called_paths(backend)
        self.assertIn(gdb, called)  # the .gdb itself is listed as a container
        self.assertNotIn(inner, called)  # we do NOT walk into it
        self.assertIn("feature_class_1", out)

    def test_show_a_directory_dataset_directly(self):
        root = tempfile.mkdtemp(prefix="niva_show_")
        gdb = os.path.join(root, "archive.gdb")
        os.makedirs(gdb)
        backend = MockBackend()
        backend.layer_map = {gdb: ["fc1"]}
        out = self._run(f'show "{gdb}"', backend)
        self.assertIn(gdb, self._called_paths(backend))
        self.assertIn("fc1", out)

    def test_deep_flag_is_harmless_on_a_file(self):
        root = tempfile.mkdtemp(prefix="niva_show_")
        gpkg = os.path.join(root, "data.gpkg")
        open(gpkg, "w").close()
        out = self._run(f'show "{gpkg}" deep', MockBackend())
        self.assertIn("layer_a", out)

    # --- database connections -----------------------------------------------

    def test_show_a_bare_connection_lists_all_tables(self):
        backend = MockBackend()
        out = self._run("show @pg", backend)
        self.assertIn(("list_tables", "pg", None, None), backend.calls)
        self.assertIn("roads", out)
        self.assertIn("@pg.roads", out)

    def test_show_a_schema_scope(self):
        backend = MockBackend()
        self._run("show @pg.public", backend)
        self.assertIn(("list_tables", "pg", "public", None), backend.calls)

    def test_show_a_single_table(self):
        backend = MockBackend()
        self._run("show @pg.public.roads", backend)
        self.assertIn(("list_tables", "pg", "public", "roads"), backend.calls)

    def test_show_resolves_a_connection_name_containing_dots(self):
        class DottedBackend(MockBackend):
            def connection_names(self):
                return ["actual_spatialite.sqlite", "pg"]

        backend = DottedBackend()
        self._run("show @actual_spatialite.sqlite", backend)
        # The whole dotted name is the connection — not conn=actual_spatialite, table=sqlite.
        self.assertIn(
            ("list_tables", "actual_spatialite.sqlite", None, None), backend.calls
        )

    def test_resolves_table_under_a_dotted_connection_name(self):
        class DottedBackend(MockBackend):
            def connection_names(self):
                return ["my.db"]

        backend = DottedBackend()
        self._run("show @my.db.roads", backend)  # conn=my.db, then schema=roads
        self.assertIn(("list_tables", "my.db", "roads", None), backend.calls)

    def test_unknown_connection_falls_back_to_first_segment(self):
        backend = MockBackend()  # connection_names() == ["pg", "sl"]
        self._run("show @nope.table", backend)
        self.assertIn(("list_tables", "nope", "table", None), backend.calls)

    # --- remote services -----------------------------------------------------

    def test_show_a_service_url_routes_to_list_service(self):
        backend = MockBackend()
        out = self._run('show "https://h/geoserver/wfs?service=WFS"', backend)
        self.assertIn(
            ("list_service", "https://h/geoserver/wfs?service=WFS"), backend.calls
        )
        self.assertIn("topp:states", out)
        self.assertIn("layers", out)  # service noun is "layer(s)", not "dataset(s)"

    def test_show_a_wfs_prefixed_url(self):
        backend = MockBackend()
        self._run('show "WFS:https://h/x"', backend)
        self.assertIn(("list_service", "WFS:https://h/x"), backend.calls)

    def test_service_url_is_not_treated_as_a_path(self):
        backend = MockBackend()
        self._run('show "http://h/wms?service=WMS"', backend)
        self.assertFalse(any(c[0] == "list_layers" for c in backend.calls))

    def test_service_error_becomes_a_flow_error(self):
        class BoomBackend(MockBackend):
            def list_service(self, url):
                raise ConnectionError("network down")

        with self.assertRaises(FlowError):
            flow('show "https://h/wfs?service=WFS"', backend=BoomBackend())

    # --- output + errors -----------------------------------------------------

    def test_show_to_file(self):
        root = tempfile.mkdtemp(prefix="niva_show_")
        out = os.path.join(root, "listing.md")
        flow(f'show @pg to="{out}"', backend=MockBackend())
        self.assertTrue(os.path.exists(out))
        with open(out) as fh:
            self.assertIn("Data at", fh.read())

    def test_show_requires_a_location(self):
        with self.assertRaises(FlowError):
            flow("show", backend=MockBackend())

    def test_show_requires_exactly_one_location(self):
        with self.assertRaises(FlowError):
            flow("show a.gpkg b.gpkg", backend=MockBackend())

    def test_show_rejects_unknown_options(self):
        with self.assertRaises(FlowError):
            flow("show @pg bogus=1", backend=MockBackend())

    def test_show_missing_path_is_a_flow_error(self):
        with self.assertRaises(FlowError):
            flow("show /no/such/place_xyz.gpkg", backend=MockBackend())

    def test_empty_connection_ref_is_a_flow_error(self):
        with self.assertRaises(FlowError):
            flow("show @", backend=MockBackend())


class TestProfileIniParse(unittest.TestCase):
    """`_connections_in_ini` — parse a QGIS settings ini for DB connection names per
    profile, without QGIS. Covers the section layouts QGIS uses for each provider."""

    def _parse(self, body):
        from niva.environment import _connections_in_ini

        path = os.path.join(tempfile.mkdtemp(prefix="niva_ini_"), "QGIS4.ini")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(body)
        return _connections_in_ini(path)

    def test_postgres_and_spatialite_and_geopackage(self):
        got = self._parse(
            "[PostgreSQL]\n"
            "connections\\gisdb3\\host=db.example.org\n"
            "connections\\gisdb3\\port=5432\n"
            "connections\\warehouse\\host=h2\n"
            "[SpatiaLite]\n"
            "connections\\actual.sqlite\\sqlitepath=/data/actual.sqlite\n"
            "[connections]\n"
            "ogr\\GPKG\\connections\\basemap.gpkg\\path=/data/basemap.gpkg\n"
            "xyz\\items\\OpenStreetMap\\http-header=x\n"  # not a DB conn — must be ignored
        )
        self.assertEqual(got.get("postgres"), ["gisdb3", "warehouse"])
        self.assertEqual(got.get("spatialite"), ["actual.sqlite"])
        self.assertEqual(got.get("ogr"), ["basemap.gpkg"])

    def test_missing_file_is_empty(self):
        from niva.environment import _connections_in_ini

        self.assertEqual(_connections_in_ini("/no/such/profile.ini"), {})


class TestInfo(unittest.TestCase):
    """The `info` verb — environment report. MockBackend records the call and returns a
    stub; the live-QGIS report contents are exercised in tests/test_pyqgis.py."""

    def test_info_records_the_backend_call_and_prints(self):
        backend = MockBackend()
        flow("info", backend=backend)
        self.assertIn(("environment_report",), backend.calls)

    def test_info_writes_report_to_file(self):
        root = tempfile.mkdtemp(prefix="niva_info_")
        out = os.path.join(root, "env.md")
        backend = MockBackend()
        flow(f'info to="{out}"', backend=backend)
        self.assertTrue(os.path.exists(out))
        report = open(out).read()
        self.assertIn("niva — environment", report)
        self.assertIn(("environment_report",), backend.calls)

    def test_info_rejects_an_input_argument(self):
        with self.assertRaises(FlowError):
            flow("info something.qgs", backend=MockBackend())

    def test_info_rejects_unknown_options(self):
        with self.assertRaises(FlowError):
            flow("info bogus=1", backend=MockBackend())


class TestExpandPath(unittest.TestCase):
    def test_expands_env_vars_and_tilde(self):
        import os

        from niva.utilities import expand_path

        os.environ["NIVA_TEST_VAR"] = "/tmp/nivatest"
        self.assertEqual(expand_path("$NIVA_TEST_VAR/x.tif"), "/tmp/nivatest/x.tif")
        self.assertEqual(expand_path("${NIVA_TEST_VAR}/x.tif"), "/tmp/nivatest/x.tif")
        self.assertEqual(expand_path("~/x.tif"), os.path.expanduser("~/x.tif"))

    def test_unset_var_left_as_is(self):
        from niva.utilities import expand_path

        self.assertEqual(
            expand_path("$NIVA_DEFINITELY_UNSET/x"), "$NIVA_DEFINITELY_UNSET/x"
        )

    def test_facet_pointcloud(self):
        from niva.utilities import facet_for_ext

        for ext in (".las", ".laz", ".e57", ".bpf", ".pts", ".ptx", ".pcd", ".vpc"):
            self.assertEqual(facet_for_ext(ext), "pointcloud", ext)
        self.assertEqual(facet_for_ext(".gpkg"), "vector")
        self.assertEqual(facet_for_ext(".tif"), "raster")


class TestSecondaryLayerPathExpansion(unittest.TestCase):
    """A `$VAR`/`~` path bound to a *secondary* param — an overlay layer (clip) or a
    raster input (zonalstats) — must reach the backend expanded, exactly like a primary
    load/save path. Regression: it used to be passed through verbatim, so `clip $O/aoi.gpkg`
    looked for a literal `$O/…` file."""

    def _clip_overlay(self, overlay_arg):
        os.environ["NIVA_TEST_OUT"] = "/tmp/nivaout"
        mb = MockBackend()
        flow(f"load a.gpkg | clip {overlay_arg} | save out.gpkg", backend=mb)
        run = next(c for c in mb.calls if c[0] == "run" and c[1] == "native:clip")
        return run[2]["OVERLAY"]

    def test_clip_overlay_expands_env_var(self):
        self.assertEqual(
            self._clip_overlay("$NIVA_TEST_OUT/aoi.gpkg"), "/tmp/nivaout/aoi.gpkg"
        )

    def test_clip_overlay_expands_tilde(self):
        self.assertEqual(
            self._clip_overlay("~/aoi.gpkg"), os.path.expanduser("~/aoi.gpkg")
        )

    def test_zonalstats_raster_expands_env_var(self):
        os.environ["NIVA_TEST_OUT"] = "/tmp/nivaout"
        mb = MockBackend()
        flow(
            "load a.gpkg | zonalstats raster=$NIVA_TEST_OUT/dem.tif stats=mean | save o.gpkg",
            backend=mb,
        )
        run = next(
            c for c in mb.calls if c[0] == "run" and c[1] == "native:zonalstatisticsfb"
        )
        self.assertEqual(run[2]["INPUT_RASTER"], "/tmp/nivaout/dem.tif")


if __name__ == "__main__":
    unittest.main()
