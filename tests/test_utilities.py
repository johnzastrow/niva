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
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def starttls(self, context=None): sent["starttls"] = True
            def login(self, u, p): sent["login"] = u
            def send_message(self, msg): sent["to"] = msg["To"]

        import smtplib
        orig = smtplib.SMTP
        smtplib.SMTP = FakeSMTP
        try:
            utilities.send_email(
                to="dest@example.com", subject="hi",
                env={"NIVA_SMTP_FROM": "me@gmail.com", "NIVA_SMTP_USER": "me@gmail.com",
                     "NIVA_SMTP_PASSWORD": "app-password"},
            )
        finally:
            smtplib.SMTP = orig
        self.assertEqual(sent["host"], "smtp.gmail.com")
        self.assertEqual(sent["port"], 587)
        self.assertTrue(sent["starttls"])           # TLS enforced
        self.assertEqual(sent["to"], "dest@example.com")

    def test_email_verb_passes_options_through(self):
        captured = {}

        def fake(**kw):
            captured.update(kw)
            return kw["to"]

        orig = utilities.send_email
        utilities.send_email = fake
        try:
            flow('email to=me@example.com subject="done" body="ok"', backend=MockBackend())
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


if __name__ == "__main__":
    unittest.main()
