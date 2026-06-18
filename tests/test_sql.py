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


class TestSqlExecute(unittest.TestCase):
    """Non-SELECT `sql` routes to execute_sql (a terminal server-side write);
    SELECT-style queries keep returning a pipeable layer via run_sql."""

    def test_select_routes_to_run_sql(self):
        backend, _ = run('sql @pg "SELECT * FROM homes"')
        self.assertEqual(backend.calls[0], ("sql", "pg", "SELECT * FROM homes"))

    def test_create_routes_to_execute(self):
        backend, _ = run('sql @pg "CREATE TABLE t AS SELECT 1 AS a"')
        self.assertEqual(backend.calls[0], ("execute_sql", "pg", "CREATE TABLE t AS SELECT 1 AS a"))

    def test_update_and_insert_and_drop_route_to_execute(self):
        for stmt in ("UPDATE homes SET x = 1", "INSERT INTO t VALUES (1)", "DROP TABLE t"):
            backend, _ = run(f'sql @pg "{stmt}"')
            self.assertEqual(backend.calls[0], ("execute_sql", "pg", stmt))

    def test_with_select_is_a_query(self):
        # A CTE leads with WITH and still returns rows — route to run_sql.
        backend, _ = run('sql @pg "WITH x AS (SELECT 1) SELECT * FROM x"')
        self.assertEqual(backend.calls[0][0], "sql")

    def test_keyword_match_is_case_insensitive(self):
        backend, _ = run('sql @pg "select 1"')
        self.assertEqual(backend.calls[0][0], "sql")

    def test_execute_is_terminal(self):
        # An execute returns no layer, so a following stage has nothing to consume.
        with self.assertRaises(FlowError):
            run('sql @pg "DROP TABLE t" | buffer 5m')


class TestDbSave(unittest.TestCase):
    """`save @conn[.schema].table [mode=…]` writes a layer into a database table.
    Credentials never reach niva; only the connection name + target do."""

    def test_save_table_default_mode(self):
        backend, _ = run("load roads.gpkg | save @pg.roads")
        self.assertEqual(backend.calls[-1], ("save_table", "pg", None, "roads", "create"))

    def test_save_schema_qualified(self):
        backend, _ = run("load roads.gpkg | save @pg.public.roads")
        self.assertEqual(backend.calls[-1], ("save_table", "pg", "public", "roads", "create"))

    def test_mode_replace_and_append(self):
        for mode in ("replace", "append"):
            backend, _ = run(f"load roads.gpkg | save @pg.roads mode={mode}")
            self.assertEqual(backend.calls[-1], ("save_table", "pg", None, "roads", mode))

    def test_bad_mode_is_error(self):
        with self.assertRaises(FlowError) as ctx:
            run("load roads.gpkg | save @pg.roads mode=upsert")
        self.assertIn("mode", str(ctx.exception))

    def test_unknown_option_rejected(self):
        with self.assertRaises(FlowError):
            run("load roads.gpkg | save @pg.roads overwrite=true")

    def test_bare_connection_non_batch_is_error(self):
        with self.assertRaises(FlowError) as ctx:
            run("load roads.gpkg | save @pg")
        self.assertIn("table", str(ctx.exception))

    def test_as_layer_rejected_on_db_target(self):
        with self.assertRaises(FlowError):
            run("load roads.gpkg | save @pg.roads as roads2")

    def test_name_template_rejected_on_db_target(self):
        with self.assertRaises(FlowError):
            run('load roads.gpkg | save "@pg.{name}"')

    def test_file_save_still_rejects_options(self):
        # The DB branch must not loosen option-rejection on ordinary file saves.
        with self.assertRaises(FlowError):
            run("load roads.gpkg | save out.gpkg mode=replace")


class TestDbSaveBatch(unittest.TestCase):
    def test_batch_names_one_table_per_item(self):
        backend = MockBackend()
        # A folder `each` over two files: one save_table per item, table = item name.
        import os
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            for n in ("alpha.gpkg", "beta.gpkg"):
                open(os.path.join(d, n), "w").close()
            Engine(backend).execute(parse(f'each "{d}" | save @pg'))
        saved = [c for c in backend.calls if c[0] == "save_table"]
        tables = sorted(c[3] for c in saved)
        self.assertEqual(tables, ["alpha", "beta"])
        self.assertTrue(all(c[1] == "pg" and c[2] is None and c[4] == "create" for c in saved))

    def test_batch_schema_qualified(self):
        backend = MockBackend()
        # In a batch, the trailing qualifier is the SCHEMA (one table per item inside it).
        import os
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            for n in ("alpha.gpkg", "beta.gpkg"):
                open(os.path.join(d, n), "w").close()
            Engine(backend).execute(parse(f'each "{d}" | save @pg.niagara'))
        saved = [c for c in backend.calls if c[0] == "save_table"]
        self.assertEqual(sorted(c[3] for c in saved), ["alpha", "beta"])
        self.assertTrue(all(c[2] == "niagara" for c in saved))  # schema = niagara

    def test_batch_three_part_ref_is_error(self):
        # Naming a single table (`@conn.schema.table`) in a batch is an error.
        backend = MockBackend()
        import os
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            open(os.path.join(d, "alpha.gpkg"), "w").close()
            with self.assertRaises(FlowError):
                Engine(backend).execute(parse(f'each "{d}" | save @pg.public.roads'))


if __name__ == "__main__":
    unittest.main()
