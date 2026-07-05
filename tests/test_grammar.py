"""Grammar tests (docs/planning/10-grammar-spec.md). Pure Python — no QGIS needed.

Run: ``python -m unittest discover -s tests`` (or ``pytest`` if installed —
unittest-style tests run under pytest too).
"""

import unittest

from niva.errors import FlowError
from niva.grammar import Call, Flow, parse


class TestGrammar(unittest.TestCase):
    def one_flow(self, text):
        prog = parse(text)
        self.assertEqual(len(prog), 1)
        self.assertIsInstance(prog[0], Flow)
        return prog[0]

    # --- stages, pipes, args, options, flags --------------------------------

    def test_single_stage(self):
        f = self.one_flow("load roads.gpkg")
        self.assertEqual(len(f.stages), 1)
        self.assertEqual(f.stages[0].verb, "load")
        self.assertEqual(f.stages[0].args, ["roads.gpkg"])

    def test_pipe_chain(self):
        f = self.one_flow("load roads.gpkg | buffer 100m | save out.gpkg")
        self.assertEqual([s.verb for s in f.stages], ["load", "buffer", "save"])
        self.assertEqual(f.stages[1].args, ["100m"])

    def test_options_and_flags_mixed(self):
        f = self.one_flow("buffer 100m dissolve cap=flat segments=12")
        s = f.stages[0]
        self.assertEqual(s.verb, "buffer")
        self.assertEqual(
            s.args, ["100m", "dissolve"]
        )  # 100m positional, dissolve flag (unresolved)
        self.assertEqual(s.options, {"cap": "flat", "segments": "12"})

    def test_list_value_option(self):
        f = self.one_flow(
            "join with=census.csv field=tract fields=pop,income prefix=cen_"
        )
        self.assertEqual(
            f.stages[0].options,
            {
                "with": "census.csv",
                "field": "tract",
                "fields": "pop,income",
                "prefix": "cen_",
            },
        )

    def test_crs_value_not_an_option(self):
        f = self.one_flow("reproject EPSG:2262")
        self.assertEqual(f.stages[0].args, ["EPSG:2262"])  # ':' is not '='
        self.assertEqual(f.stages[0].options, {})

    def test_connection_token(self):
        f = self.one_flow('sql @cats_pg "SELECT * FROM homes"')
        self.assertEqual(f.stages[0].verb, "sql")
        self.assertEqual(f.stages[0].args, ["@cats_pg", "SELECT * FROM homes"])

    # --- quoting -------------------------------------------------------------

    def test_quoted_expression_keeps_inner_punct(self):
        f = self.one_flow("filter \"landuse = 'R' and area > 1000\"")
        self.assertEqual(f.stages[0].verb, "filter")
        self.assertEqual(f.stages[0].args, ["landuse = 'R' and area > 1000"])

    def test_quoted_option_value_with_spaces(self):
        f = self.one_flow('metadata set title="Cat parcels"')
        s = f.stages[0]
        self.assertEqual(s.verb, "metadata")
        self.assertEqual(s.args, ["set"])
        self.assertEqual(s.options, {"title": "Cat parcels"})

    def test_escaped_quote_in_string(self):
        f = self.one_flow('filter "\\"zone\\" = 1"')  # source: filter "\"zone\" = 1"
        self.assertEqual(f.stages[0].args, ['"zone" = 1'])

    def test_pipe_inside_quotes_is_not_a_split(self):
        f = self.one_flow('filter "a | b"')
        self.assertEqual(len(f.stages), 1)
        self.assertEqual(f.stages[0].args, ["a | b"])

    # --- comments, continuation, multiple flows ------------------------------

    def test_comment_stripped(self):
        f = self.one_flow("load roads.gpkg | buffer 100m   # a trailing comment")
        self.assertEqual([s.verb for s in f.stages], ["load", "buffer"])

    def test_hash_inside_quotes_kept(self):
        f = self.one_flow("filter \"name = '#1'\"")
        self.assertEqual(f.stages[0].args, ["name = '#1'"])

    def test_quoted_connection_ref_keeps_at_strips_quotes(self):
        # `@"name"` / `@'name'` — a connection whose name has spaces/dots must resolve, so the
        # quotes are stripped but the `@` is kept (regression: the quotes used to leak in).
        self.assertEqual(
            self.one_flow('show @"My PG Server"').stages[0].args, ["@My PG Server"]
        )
        self.assertEqual(
            self.one_flow("show @'spatialite.db'").stages[0].args, ["@spatialite.db"]
        )
        self.assertEqual(
            self.one_flow('load @"CNYTriData.gpkg.course_points"').stages[0].args,
            ["@CNYTriData.gpkg.course_points"],
        )

    def test_apostrophe_in_unquoted_token_is_literal(self):
        # A lone quote *inside* an unquoted token is data, not a delimiter — names like
        # O'Brien.shp must survive (we only strip a *surrounding* pair).
        self.assertEqual(
            self.one_flow("load O'Brien.shp").stages[0].args, ["O'Brien.shp"]
        )
        self.assertEqual(
            self.one_flow('load "O\'Brien.shp"').stages[0].args, ["O'Brien.shp"]
        )

    def test_unterminated_quote_is_a_flow_error(self):
        for bad in ('load "foo', "load 'foo", 'show @"bar'):
            with self.assertRaises(FlowError):
                parse(bad)

    def test_quoted_option_value_with_pipe_and_at(self):
        # an option value can carry niva-special chars when quoted
        f = self.one_flow('run x EXPRESSION="a|b" CONN=@db')
        self.assertEqual(f.stages[0].options, {"EXPRESSION": "a|b", "CONN": "@db"})

    def test_line_continuation_via_pipe(self):
        text = "load roads.gpkg\n  | buffer 100m\n  | save out.gpkg"
        f = self.one_flow(text)
        self.assertEqual([s.verb for s in f.stages], ["load", "buffer", "save"])

    def test_blank_line_separates_flows(self):
        prog = parse("load a.gpkg | save b.gpkg\n\nload c.gpkg | save d.gpkg")
        self.assertEqual(len(prog), 2)
        self.assertTrue(all(isinstance(p, Flow) for p in prog))

    def test_adjacent_lines_are_separate_flows(self):
        prog = parse("load a | save b\nload c | save d")
        self.assertEqual(len(prog), 2)

    # --- call statements -----------------------------------------------------

    def test_call_statement(self):
        prog = parse("call acquire.niva")
        self.assertEqual(len(prog), 1)
        self.assertIsInstance(prog[0], Call)
        self.assertEqual(prog[0].target, "acquire.niva")

    def test_call_interleaved_with_flows(self):
        prog = parse("call acquire.niva\nload x | save y\ncall report.niva")
        self.assertEqual([type(p).__name__ for p in prog], ["Call", "Flow", "Call"])

    # --- errors --------------------------------------------------------------

    def test_error_stage_starts_with_option(self):
        with self.assertRaises(FlowError):
            parse("cap=flat")

    def test_error_doubled_pipe(self):
        with self.assertRaises(FlowError):
            parse("load x | | save y")

    def test_error_call_arity(self):
        with self.assertRaises(FlowError):
            parse("call a.niva b.niva")

    def test_flowerror_names_the_line(self):
        try:
            parse("load x\ncap=flat")
        except FlowError as exc:
            self.assertEqual(exc.line, 2)
        else:
            self.fail("expected FlowError")


if __name__ == "__main__":
    unittest.main()
