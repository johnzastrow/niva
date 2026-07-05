"""Expansive tests for `validate` — the offline niva linter.

Proves it catches the full spectrum (grammar, invented/typo verbs, alias arg/option/enum
errors, cross-stage runtime failures via a MockBackend dry-run, `run <id>` params) AND lint
warnings (no-unit distance, run-has-alias, SAGA/OTB, no-save) — while producing **no false
positives** on valid flows. Pure Python, no QGIS.

Run: ``python -m unittest tests.test_validate``.
"""

import contextlib
import io
import os
import tempfile
import unittest

from niva.validate import validate_text


def check(flow, *, exercise=True):
    """(ok, [(line, severity, message)]) for a flow string."""
    return validate_text(flow, exercise=exercise)


def messages(flow, sev=None, **kw):
    _, issues = check(flow, **kw)
    return [m for _, s, m in issues if sev is None or s == sev]


def errors(flow, **kw):
    return messages(flow, sev="error", **kw)


def warnings(flow, **kw):
    return messages(flow, sev="warning", **kw)


# --------------------------------------------------------------------------- #
# No false positives — valid flows must pass clean.
# --------------------------------------------------------------------------- #
class TestAcceptsValidFlows(unittest.TestCase):
    GOOD = [
        "load a.gpkg | buffer 100m | save b.gpkg",
        "load roads.gpkg | fixgeom | reproject EPSG:6346 | clip aoi.gpkg | dissolve | save out.gpkg",
        "load a.gpkg | buffer 100m dissolve segments=12 cap=flat | save b.gpkg",
        "load a.gpkg | filter \"landuse = 'R'\" | save b.gpkg",
        "load a.copc.laz | run pdal:exportraster ATTRIBUTE=Z RESOLUTION=1 | save r.tif",
        'load t.las | run pdalcli:to_raster attribute=Z filter="Classification==2" | save d.tif',
        "load dem.tif | slope | save s.tif",
        'sql @db "SELECT * FROM parcels WHERE acres > 5" | save p.gpkg',
        "load a.gpkg | zonalstats raster=d.tif stats=mean,min prefix=z_ | save b.gpkg",
    ]

    def test_valid_flows_have_no_errors(self):
        for flow in self.GOOD:
            with self.subTest(flow=flow):
                self.assertEqual(errors(flow), [], flow)

    def test_clean_flows_have_no_warnings_either(self):
        # These are also idiomatic — zero lint noise.
        for flow in [
            "load a.gpkg | buffer 100m | save b.gpkg",
            "load dem.tif | slope | save s.tif",
        ]:
            with self.subTest(flow=flow):
                ok, issues = check(flow)
                self.assertTrue(ok)
                self.assertEqual(issues, [], flow)

    def test_harness_ids_never_warn_on_params(self):
        # pdalcli:/saga: aren't QGIS algorithms, so a param is never wrongly flagged as unknown.
        w = warnings(
            'load t.las | run pdalcli:to_raster attribute=Z filter="x==2" output=g.laz'
        )
        self.assertFalse(any("unknown parameter" in x for x in w))


# --------------------------------------------------------------------------- #
# Errors — the flow is definitively wrong (ok is False).
# --------------------------------------------------------------------------- #
class TestCatchesErrors(unittest.TestCase):
    def _has_error(self, flow, needle):
        ok, _ = check(flow)
        self.assertFalse(ok, f"expected invalid: {flow}")
        self.assertTrue(
            any(needle in m for m in errors(flow)), f"{needle!r} not in {errors(flow)}"
        )

    def test_invented_verb(self):
        self._has_error(
            "load a.gpkg | compute x=1 | save b.gpkg", "unknown verb `compute`"
        )

    def test_verb_typo_suggests(self):
        self._has_error(
            "load a.gpkg | reproj EPSG:3857 | save b.gpkg", "did you mean `reproject`?"
        )

    def test_missing_required_arg(self):
        self._has_error("load a.gpkg | buffer | save b.gpkg", "needs a `distance`")

    def test_unknown_alias_option(self):
        self._has_error(
            "load a.gpkg | buffer 100m segmentz=5 | save b.gpkg", "no option `segmentz`"
        )

    def test_bad_enum_value(self):
        self._has_error(
            "load a.gpkg | buffer 100m cap=triangle | save b.gpkg",
            "not a valid value for `cap`",
        )

    def test_transform_before_load(self):
        self._has_error("buffer 100m | save b.gpkg", "needs an input layer")

    def test_unknown_crs_fails_closed(self):
        self._has_error(
            "load a.gpkg | reproject EPSG:999999 | save b.gpkg", "not a reco"
        )

    def test_name_placeholder_outside_batch(self):
        self._has_error('load a.gpkg | save "out/{name}.gpkg"', "{name}")

    def test_run_without_id(self):
        self._has_error("load a.gpkg | run | save b.gpkg", "needs an algorithm id")

    def test_backslash_is_not_a_continuation(self):
        # `\` is not line-continuation; a stray one becomes a stray token and is rejected.
        self._has_error(
            "load a.gpkg | buffer 100m \\ dissolve | save b.gpkg", "unexpected value"
        )

    def test_grammar_unterminated_quote(self):
        self._has_error('load "a.gpkg | buffer 100m', "grammar")


# --------------------------------------------------------------------------- #
# Lint warnings — the flow runs, but the linter flags a smell (ok stays True).
# --------------------------------------------------------------------------- #
class TestLintWarnings(unittest.TestCase):
    def _warns(self, flow, needle):
        ok, _ = check(flow)
        self.assertTrue(ok, f"expected valid-with-warning: {flow}")
        self.assertTrue(
            any(needle in w for w in warnings(flow)),
            f"{needle!r} not in {warnings(flow)}",
        )

    def test_distance_without_unit(self):
        self._warns("load a.gpkg | buffer 100 | save b.gpkg", "has no unit")

    def test_run_unknown_param_suggests(self):
        self._warns(
            "load a.gpkg | run native:buffer DISTANZE=5 | save b.gpkg",
            "did you mean `DISTANCE`?",
        )

    def test_run_unknown_id(self):
        self._warns(
            "load a.gpkg | run native:notreal FOO=1 | save b.gpkg",
            "not in niva's algorithm catalog",
        )

    def test_run_when_alias_exists(self):
        self._warns(
            "load a.gpkg | run native:buffer DISTANCE=5 | save b.gpkg",
            "prefer `buffer`",
        )

    def test_saga_otb_provider_preference(self):
        self._warns("load i.tif | run otb:Smoothing type=mean | save o.tif", "SAGA/OTB")

    def test_flow_with_no_save(self):
        self._warns("load a.gpkg | buffer 100m", "no `save`")

    def test_distance_with_unit_is_clean(self):
        self.assertNotIn(
            "has no unit", " ".join(warnings("load a.gpkg | buffer 100m | save b.gpkg"))
        )


# --------------------------------------------------------------------------- #
# Subtle & large — the mistakes that slip past a human / an LLM.
# --------------------------------------------------------------------------- #
class TestSubtleAndLarge(unittest.TestCase):
    def test_stats_is_not_a_verb(self):
        # The real bug from issue #28 — `stats` is the *option* of zonalstats, not a verb.
        errs = errors("load a.gpkg | stats | save b.gpkg")
        self.assertTrue(
            any("unknown verb `stats`" in e and "zonalstats" in e for e in errs)
        )

    def test_all_errors_collected_not_just_first(self):
        flow = "load a.gpkg | compute x=1 | frobnicate | buffer 100m capp=flat | save b.gpkg"
        errs = errors(flow)
        self.assertGreaterEqual(len(errs), 2)  # compute + frobnicate at least
        self.assertTrue(any("compute" in e for e in errs))
        self.assertTrue(any("frobnicate" in e for e in errs))

    def test_large_broken_flow_is_rejected(self):
        flow = "\n".join(
            [
                "load a.gpkg | reproj EPSG:3857 | save b.gpkg",  # typo verb
                "buffer 100 | compute q=1 | save c.gpkg",  # transform-first + invented
                "load d.gpkg | zonalstats stats=mean | save e.gpkg",  # missing raster= (bind error)
            ]
        )
        ok, issues = check(flow)
        self.assertFalse(ok)
        self.assertGreaterEqual(sum(1 for _, s, _ in issues if s == "error"), 2)

    def test_plausible_but_wrong_enum(self):
        # `square` is valid for cap; `squared` is not — a subtle typo.
        self.assertEqual(
            errors("load a.gpkg | buffer 100m cap=square | save b.gpkg"), []
        )
        self.assertTrue(errors("load a.gpkg | buffer 100m cap=squared | save b.gpkg"))


# --------------------------------------------------------------------------- #
# The dry-run "exercise" — the part that makes a pass mean "runnable".
# --------------------------------------------------------------------------- #
class TestExerciseCatchesRuntime(unittest.TestCase):
    def test_static_only_misses_cross_stage(self):
        # transform-before-load is grammatically fine per stage; only the dry-run catches it.
        self.assertEqual(errors("buffer 100m | save b.gpkg", exercise=False), [])
        self.assertTrue(errors("buffer 100m | save b.gpkg", exercise=True))

    def test_data_dependent_is_warning_not_error(self):
        # `each` over a glob with no matching files → warning (needs data), never a false error.
        ok, issues = check(
            'each "tiles/*.tif" | warp EPSG:3857 | save "out/{name}.tif"'
        )
        self.assertTrue(ok)
        self.assertTrue(any("needs data" in m for _, s, m in issues if s == "warning"))


# --------------------------------------------------------------------------- #
# CLI — `niva validate <file...>` exit codes and reporting.
# --------------------------------------------------------------------------- #
class TestValidateCLI(unittest.TestCase):
    def _run(self, *args):
        from niva.cli.main import main

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            code = main(["validate", *args])
        return code, buf.getvalue()

    def _write(self, text):
        fd, path = tempfile.mkstemp(suffix=".niva")
        os.write(fd, text.encode())
        os.close(fd)
        return path

    def test_good_file_exits_zero(self):
        p = self._write("load a.gpkg | buffer 100m | save b.gpkg\n")
        try:
            code, out = self._run(p)
            self.assertEqual(code, 0)
            self.assertIn("✓", out)
            self.assertIn("0 error(s)", out)
        finally:
            os.unlink(p)

    def test_bad_file_exits_nonzero(self):
        p = self._write("load a.gpkg | compute x=1 | save b.gpkg\n")
        try:
            code, out = self._run(p)
            self.assertEqual(code, 1)
            self.assertIn("unknown verb `compute`", out)
        finally:
            os.unlink(p)

    def test_missing_file_reported(self):
        code, out = self._run("/no/such/file.niva")
        self.assertEqual(code, 1)

    def test_no_args_usage(self):
        code, _ = self._run()
        self.assertEqual(code, 2)


# --------------------------------------------------------------------------- #
# The dry-run exercise must be SIDE-EFFECT-FREE — a linter never touches disk,
# the network, or existing files (engine `inert=True`).
# --------------------------------------------------------------------------- #
class TestExerciseHasNoSideEffects(unittest.TestCase):
    def test_assess_report_is_not_written(self):
        d = tempfile.mkdtemp()
        report = os.path.join(d, "quality.md")
        ok, _ = check(f'load a.gpkg | assess to "{report}" | save b.gpkg')
        self.assertTrue(ok)
        self.assertFalse(
            os.path.exists(report), "validate must not write the assessment report"
        )

    def test_catalog_output_is_not_written(self):
        d = tempfile.mkdtemp()
        out = os.path.join(d, "catalog.md")
        check(f'catalog "{d}" to="{out}"')
        self.assertFalse(
            os.path.exists(out), "validate must not write the catalog file"
        )

    def test_remove_does_not_delete(self):
        fd, victim = tempfile.mkstemp(suffix=".gpkg")
        os.close(fd)
        try:
            ok, _ = check(f'remove "{victim}" force')
            self.assertTrue(os.path.exists(victim), "validate must NEVER delete a file")
        finally:
            if os.path.exists(victim):
                os.unlink(victim)

    def test_notify_is_not_sent(self):
        import niva.utilities as u

        original = u.send_ntfy
        u.send_ntfy = lambda *a, **k: (_ for _ in ()).throw(
            AssertionError("send_ntfy called during validate")
        )
        try:
            ok, _ = check('load a.gpkg | notify "done {ops}" to=topic | save b.gpkg')
            self.assertTrue(ok)  # completed without ever calling send_ntfy
        finally:
            u.send_ntfy = original

    def test_email_is_not_sent(self):
        import niva.utilities as u

        original = u.send_email
        u.send_email = lambda *a, **k: (_ for _ in ()).throw(
            AssertionError("send_email called during validate")
        )
        try:
            ok, _ = check(
                "load a.gpkg | email to=x@example.com subject=hi | save b.gpkg"
            )
            self.assertTrue(ok)
        finally:
            u.send_email = original


if __name__ == "__main__":
    unittest.main()
