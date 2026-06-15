"""`@conn` loading and `sql` tests (docs/planning/02, connections.py). Mock-backed.

Run: ``python -m unittest discover -s tests`` (or ``pytest``).
"""

import unittest

from niva.engine import Engine, MockBackend
from niva.engine.connections import parse_connection_ref
from niva.errors import FlowError
from niva.grammar import parse


def run(text):
    backend = MockBackend()
    result = Engine(backend).execute(parse(text))
    return backend, result


class TestRefParsing(unittest.TestCase):
    def test_bare(self):
        self.assertEqual(parse_connection_ref("@pg"), ("pg", None, None))

    def test_table(self):
        self.assertEqual(parse_connection_ref("@pg.roads"), ("pg", None, "roads"))

    def test_schema_table(self):
        self.assertEqual(parse_connection_ref("@pg.public.roads"), ("pg", "public", "roads"))

    def test_empty_raises(self):
        with self.assertRaises(ValueError):
            parse_connection_ref("@")


class TestLoadConnection(unittest.TestCase):
    def test_load_table(self):
        backend, _ = run("load @cats_pg.human_homes | save out.gpkg")
        self.assertEqual(backend.calls[0], ("load_table", "cats_pg", None, "human_homes"))

    def test_load_schema_table(self):
        backend, _ = run("load @pg.public.roads")
        self.assertEqual(backend.calls[0], ("load_table", "pg", "public", "roads"))

    def test_at_ref_that_looks_like_a_file_hints_the_path_form(self):
        # `@example.gpkg` is a common slip — `@` is for connections, files use a path
        with self.assertRaises(FlowError) as ctx:
            run("load @example.gpkg")
        msg = str(ctx.exception)
        self.assertIn("looks like a file", msg)
        self.assertIn("layername=", msg)

    def test_load_bare_connection_is_error(self):
        with self.assertRaises(FlowError) as ctx:
            run("load @cats_pg")
        self.assertIn("table", str(ctx.exception))

    def test_load_table_then_pipe(self):
        backend, _ = run("load @pg.roads | buffer 10m | save o.gpkg")
        self.assertEqual([c[0] for c in backend.calls], ["load_table", "run", "save"])


class TestSql(unittest.TestCase):
    def test_sql_runs_query(self):
        backend, _ = run('sql @cats_pg "SELECT * FROM homes WHERE has_cat" | save t.gpkg')
        self.assertEqual(backend.calls[0], ("sql", "cats_pg", "SELECT * FROM homes WHERE has_cat"))
        self.assertEqual(backend.calls[1][0], "save")

    def test_sql_result_is_pipeable(self):
        backend, _ = run('sql @pg "SELECT 1" | buffer 5m | save o.gpkg')
        self.assertEqual([c[0] for c in backend.calls], ["sql", "run", "save"])

    def test_sql_needs_connection_and_query(self):
        with self.assertRaises(FlowError):
            run('sql "SELECT 1"')  # missing connection

    def test_sql_rejects_table_ref(self):
        with self.assertRaises(FlowError) as ctx:
            run('sql @pg.roads "SELECT 1"')
        self.assertIn("bare connection", str(ctx.exception))

    def test_sql_first_arg_must_be_connection(self):
        with self.assertRaises(FlowError):
            run('sql notaconn "SELECT 1"')


if __name__ == "__main__":
    unittest.main()
