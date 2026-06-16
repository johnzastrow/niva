"""The niva dock — a flow editor with Run / Dry-run, output, and map integration.

All Qt access goes through ``qgis.PyQt`` so it works on QGIS 3 (Qt5) and QGIS 4
(Qt6). Flows run in-process on the GUI thread (v0.1): fine for interactive work;
long jobs block the UI — threading is a later increment (cf. Oscar A9: flows are
serial within a process anyway).
"""

from __future__ import annotations

import os
import tempfile
from datetime import datetime

from qgis.PyQt.QtGui import QFont, QPalette
from qgis.PyQt.QtWidgets import (
    QCheckBox,
    QDockWidget,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QTabWidget,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from . import environment, runner

# Persisted settings keys (QgsSettings) and the default run-log folder.
_LOG_ENABLED_KEY = "niva/log_enabled"
_LOG_DIR_KEY = "niva/log_dir"

# Mask password/token fields. Qt6 scopes the enum; Qt5 exposes it flat.
try:
    _PW_ECHO = QLineEdit.EchoMode.Password
except AttributeError:  # pragma: no cover — Qt5 path
    _PW_ECHO = QLineEdit.Password

# The environment the `email` / `notify` verbs read (niva.utilities). Each row is
# (env var, label, secret?, placeholder, detailed tooltip). Non-secret values are
# remembered in QgsSettings; secrets (password/token) are applied for the session
# only — never written to disk — to keep credentials out of the QGIS config files.
_ENV_FIELDS = [
    ("NIVA_NTFY_TOPIC", "ntfy topic", False, "my-niva-topic",
     "The ntfy topic a `notify` step publishes to. Subscribe to this same topic in the "
     "ntfy app or at <server>/<topic> to receive the messages. A flow's `notify` uses "
     "this unless it sets its own `to=`."),
    ("NIVA_NTFY_SERVER", "ntfy server", False, "https://ntfy.sh",
     "The ntfy server base URL. Leave as https://ntfy.sh for the public service, or "
     "point at your self-hosted ntfy. Messages POST to <server>/<topic>."),
    ("NIVA_NTFY_TOKEN", "ntfy token", True, "(optional, for protected topics)",
     "Optional bearer token for a protected/private ntfy topic. Sent as an "
     "Authorization header; never logged. Session-only — not written to disk (use the "
     "QGIS encrypted store below to persist it)."),
    ("NIVA_SMTP_HOST", "SMTP host", False, "smtp.gmail.com (auto for @gmail.com)",
     "SMTP server hostname for the `email` verb. Leave blank for Gmail — a @gmail.com "
     "From/User auto-selects smtp.gmail.com:587."),
    ("NIVA_SMTP_PORT", "SMTP port", False, "587",
     "SMTP port. 587 (STARTTLS) is the default; 465 uses implicit TLS. TLS is always "
     "required — niva will not send over an unencrypted connection."),
    ("NIVA_SMTP_USER", "SMTP user", False, "you@gmail.com",
     "Username to authenticate to the SMTP server (usually your full email address)."),
    ("NIVA_SMTP_FROM", "From address", False, "you@gmail.com",
     "The From address on sent mail. Defaults to the SMTP user if left blank. A "
     "@gmail.com value here also triggers the Gmail host auto-default."),
    ("NIVA_SMTP_PASSWORD", "Password / App Password", True, "Gmail: an App Password",
     "SMTP password. For Gmail this must be an App Password (with 2-Step Verification "
     "on), NOT your account password. Never logged; session-only unless saved to the "
     "QGIS encrypted store below."),
]
_ENV_SETTINGS_PREFIX = "niva/env/"
# QgsAuthManager config IDs for the persisted secrets (the secrets live encrypted in
# QGIS's auth DB; only these non-secret IDs are kept in QgsSettings).
_SMTP_AUTHCFG_KEY = "niva/smtp_authcfg"
_NTFY_AUTHCFG_KEY = "niva/ntfy_authcfg"


def default_log_dir() -> str:
    return os.path.join(tempfile.gettempdir(), "niva_logs")

_SAMPLE = """\
# Edit this flow, then click Run — it executes in this QGIS session.
# A GeoPackage holds many layers, so name one with |layername=.
# Example:
#   load "/path/to/data.gpkg|layername=roads" | buffer 100m dissolve | save /tmp/out.gpkg
"""


class NivaDock(QDockWidget):
    def __init__(self, iface):
        super().__init__("niva", iface.mainWindow())
        self.iface = iface
        self.path = None  # the .niva file currently open, if any (for relative paths)
        # One log file per QGIS session: a stamp fixed for the dock's lifetime, so all
        # runs append to the same journal until the user hits Reset (new stamp). The
        # microseconds keep a Reset within the same second from reusing the file.
        self._session_id = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        self.setObjectName("NivaDock")

        self.tabs = QTabWidget(self)
        self.tabs.addTab(self._build_flow_tab(), "Flow")
        self.tabs.addTab(self._build_convert_tab(), "Convert")
        self.tabs.addTab(self._build_setup_tab(), "Setup")
        self.setWidget(self.tabs)

    def _build_flow_tab(self) -> QWidget:
        tab = QWidget(self)
        layout = QVBoxLayout(tab)

        # The editor is the only thing you type into — leave it the theme's editable
        # field color (a white-ish "Base") so it reads as an input.
        self.editor = QPlainTextEdit(tab)
        self.editor.setPlainText(_SAMPLE)
        self.editor.setFont(_mono())
        self.editor.setToolTip(
            "Write a niva flow here. A flow is a chain of verb stages joined by | , read "
            "left to right; each stage's output feeds the next. Example:\n"
            '  load "data.gpkg|layername=roads" | buffer 100m dissolve | save /tmp/out.gpkg\n'
            "Multiple flows: one per line (blank line separates). A line starting with # "
            "is a comment. `each \"dir\"` runs the rest once per file/layer; `run <id> "
            "KEY=value` reaches any QGIS algorithm. Click Run to execute, or Dry-run to "
            "validate without touching data."
        )
        layout.addWidget(self.editor, 3)

        buttons = QHBoxLayout()
        open_btn = QPushButton("Open…", tab)
        open_btn.setToolTip("Open a .niva flow file from disk into the editor above, "
                            "replacing its contents (e.g. examples/analyst_plan.niva). "
                            "Then edit it or click Run.")
        open_btn.clicked.connect(self._open)
        self.run_btn = QPushButton("Run", tab)
        self.run_btn.setToolTip(
            "Execute the flow for real against your data, in this QGIS session. Runs in "
            "the background so QGIS stays responsive; progress streams to the output "
            "panel below and the final output layer is added to the map. Disabled while "
            "a run is in progress (one flow at a time). The Setup-tab email/notify "
            "settings are applied just before the run.")
        self.run_btn.clicked.connect(self._run)
        self.dry_btn = QPushButton("Dry-run", tab)
        self.dry_btn.setToolTip(
            "Validate the flow without executing it or writing any data: parses every "
            "stage, resolves each verb to its QGIS algorithm + parameters, checks "
            "CRS/units, and lists what it would run. Fast and safe — check a flow before "
            "a real Run.")
        self.dry_btn.clicked.connect(self._dry_run)
        self.cancel_btn = QPushButton("Stop", tab)
        self.cancel_btn.setToolTip(
            "Stop the flow that is currently running. Enabled only during a run; cancels "
            "the background task as soon as the running algorithm next checks for "
            "cancellation (a single long GDAL step can take a moment to stop). Any "
            "partial output already written stays on disk.")
        self.cancel_btn.clicked.connect(self._cancel)
        self.cancel_btn.setEnabled(False)
        clear_btn = QPushButton("Clear output", tab)
        clear_btn.setToolTip("Clear the text in the output panel below. On-screen only — "
                             "it does not affect your flow, your data, or the on-disk "
                             "run log.")
        clear_btn.clicked.connect(self._clear)
        for b in (open_btn, self.run_btn, self.dry_btn, self.cancel_btn, clear_btn):
            buttons.addWidget(b)
        buttons.addStretch(1)
        self.path_label = QLabel("(unsaved flow)", tab)
        buttons.addWidget(self.path_label)
        layout.addLayout(buttons)

        # Read-only output recedes into the dialog (window colour) so it doesn't look
        # like another input — only the editor above stands out as typeable.
        self.output = QPlainTextEdit(tab)
        self.output.setReadOnly(True)
        self.output.setFont(_mono())
        self.output.setToolTip("Run messages, progress, and results appear here "
                               "(read-only)")
        _recede(self.output)
        layout.addWidget(self.output, 2)
        return tab

    def _build_convert_tab(self) -> QWidget:
        tab = QWidget(self)
        layout = QVBoxLayout(tab)

        note = QLabel(
            "<b>Export</b> turns the flow in the Flow tab into a standalone PyQGIS "
            "<code>.py</code> script (one <code>processing.run(…)</code> per step) — "
            "to learn from, customise, or hand to a developer.<br>"
            "<b>Import</b> reads a script back into a flow, but <b>only niva-shaped "
            "scripts</b> — a flat list of <code>processing.run(…)</code> calls (such as "
            "the ones Export produces, edited or not). Arbitrary PyQGIS cannot be "
            "imported: niva is a linear pipeline; loops, conditionals and custom "
            "functions have no equivalent and are reported, not guessed.",
            tab,
        )
        note.setWordWrap(True)
        layout.addWidget(note)

        erow = QHBoxLayout()
        export_btn = QPushButton("Export Flow → .py", tab)
        export_btn.setToolTip("Transpile the flow in the Flow tab into an equivalent, "
                              "runnable standalone PyQGIS script (one processing.run per "
                              "step), shown in the panel below. niva's 'eject hatch' — "
                              "learn the PyQGIS, customise it, or hand it off.")
        export_btn.clicked.connect(self._export_to_py)
        save_btn = QPushButton("Save .py…", tab)
        save_btn.setToolTip("Save the PyQGIS script shown in the panel below to a .py "
                            "file on disk. Run the saved script with QGIS's own Python, "
                            "or hand it to a developer to customise.")
        save_btn.clicked.connect(self._save_py)
        import_btn = QPushButton("Import .py…", tab)
        import_btn.setToolTip("Convert a PyQGIS script back into a flow. Uses the "
                              "script shown below if you just exported/edited one, "
                              "otherwise prompts for a .py file. Only niva-shaped "
                              "scripts (a flat list of processing.run calls) import.")
        import_btn.clicked.connect(self._import_from_py)
        self.send_to_flow_btn = QPushButton("Send to Flow tab", tab)
        self.send_to_flow_btn.setToolTip("Load the imported flow into the Flow tab's "
                                         "editor so you can run it (enabled after an import)")
        self.send_to_flow_btn.clicked.connect(self._send_to_flow)
        self.send_to_flow_btn.setEnabled(False)
        for b in (export_btn, save_btn, import_btn, self.send_to_flow_btn):
            erow.addWidget(b)
        erow.addStretch(1)
        layout.addLayout(erow)

        # The preview holds whatever was last produced — generated .py (export) or
        # recovered .niva (import). Editable .py here can be re-imported via Import…
        self.convert_view = QPlainTextEdit(tab)
        self.convert_view.setFont(_mono())
        self.convert_view.setToolTip(
            "Shows the exported PyQGIS script or the imported flow. You can edit an "
            "exported script here (add/change processing.run params) and click "
            "Import .py… to round-trip the changes back into a flow."
        )
        layout.addWidget(self.convert_view, 1)

        self.convert_status = QLabel("", tab)
        self.convert_status.setWordWrap(True)
        self.convert_status.setToolTip("Status of the last export/import, including "
                                       "any warnings about parts that could not be imported")
        layout.addWidget(self.convert_status)

        self._last_export = ""   # generated .py text, for Save .py…
        self._last_import = ""   # recovered .niva text, for Send to Flow tab
        return tab

    def _build_setup_tab(self) -> QWidget:
        from qgis.core import QgsSettings

        tab = QWidget(self)
        layout = QVBoxLayout(tab)

        # --- Settings: the per-session run log -------------------------------
        settings = QgsSettings()
        self.log_enabled = QCheckBox("Log each run to one file per QGIS session", tab)
        self.log_enabled.setToolTip(
            "When on, each run appends to a per-session journal: a human-readable "
            ".log (one line per operation) and a machine-readable .jsonl. Off = no "
            "logging. Credentials and SQL text are never written to the log."
        )
        self.log_enabled.setChecked(settings.value(_LOG_ENABLED_KEY, True, type=bool))
        self.log_enabled.toggled.connect(self._on_log_enabled)
        layout.addWidget(self.log_enabled)

        row = QHBoxLayout()
        row.addWidget(QLabel("Log folder:", tab))
        self.log_dir = QLineEdit(
            settings.value(_LOG_DIR_KEY, default_log_dir(), type=str), tab
        )
        self.log_dir.setToolTip("Folder where the per-session run log is written "
                                "(<session>.log human-readable + <session>.jsonl "
                                "machine-readable). Edit the path or use Browse…")
        self.log_dir.editingFinished.connect(self._on_log_dir_edited)
        browse = QPushButton("Browse…", tab)
        browse.setToolTip("Choose the folder where per-session run logs are written, "
                          "via a folder picker (fills in the Log folder field).")
        browse.clicked.connect(self._browse_log_dir)
        row.addWidget(self.log_dir)
        row.addWidget(browse)
        layout.addLayout(row)

        srow = QHBoxLayout()
        srow.addWidget(QLabel("Session log:", tab))
        self.session_label = QLabel(tab)
        self.session_label.setTextInteractionFlags(self.session_label.textInteractionFlags())
        self.session_label.setToolTip("The log file the current session is appending to")
        reset = QPushButton("Reset (new file)", tab)
        reset.setToolTip("Start a fresh log file — subsequent runs append to the new "
                         "one instead of the current session's file")
        reset.clicked.connect(self._reset_session_log)
        srow.addWidget(self.session_label, 1)
        srow.addWidget(reset)
        layout.addLayout(srow)
        self._update_session_label()

        # --- Email & notifications (the env the email/notify verbs read) -----
        layout.addWidget(_section_label("Email &amp; notifications", tab))
        note = QLabel(
            "Fill these in to use the <code>email</code> and <code>notify</code> verbs. "
            "<b>Gmail:</b> just set <i>SMTP user</i>/<i>From</i> to your address and "
            "<i>Password</i> to a Gmail <b>App Password</b> (host is filled in "
            "automatically). Non-secret fields are remembered; the <b>password and "
            "token can be saved to QGIS's <b>encrypted store</b> (button below, unlocked "
            "by your QGIS master password) — or, if you don't save them, they apply for "
            "this session only and are never written to disk. Non-secret fields are "
            "remembered as plain settings.",
            tab,
        )
        note.setWordWrap(True)
        layout.addWidget(note)

        self._env_fields = {}  # env var -> (QLineEdit, secret?)
        for env, label, secret, placeholder, help_text in _ENV_FIELDS:
            erow = QHBoxLayout()
            lbl = QLabel(label + ":", tab)
            lbl.setMinimumWidth(150)
            le = QLineEdit(tab)
            le.setPlaceholderText(placeholder)
            le.setToolTip(f"{help_text}\n\n(Sets the {env} environment variable"
                          + (", session only — not written to disk.)" if secret
                             else ", remembered across sessions.)"))
            if secret:
                le.setEchoMode(_PW_ECHO)
            # Prefill from the live environment; non-secrets fall back to saved
            # settings (and are pushed live so saved config works before "Apply").
            value = os.environ.get(env, "")
            if not value and not secret:
                value = settings.value(_ENV_SETTINGS_PREFIX + env, "", type=str)
                if value:
                    os.environ[env] = value
            le.setText(value)
            self._env_fields[env] = (le, secret)
            erow.addWidget(lbl)
            erow.addWidget(le, 1)
            layout.addLayout(erow)

        # Boolean alert flags → ntfy a message automatically on errors / warnings.
        self._env_flags = {}  # env var -> QCheckBox
        frow = QHBoxLayout()
        for env, label, tip in (
            ("NIVA_NTFY_ON_ERROR", "Notify on errors",
             "Send a high-priority ntfy message if a run fails"),
            ("NIVA_NTFY_ON_WARNING", "Notify on warnings",
             "Send an ntfy message on warnings (mixed geometry, datum-transform, "
             "skipped batch items) — de-duplicated per run"),
        ):
            cb = QCheckBox(label, tab)
            cb.setToolTip(tip + f" (sets {env})")
            on = os.environ.get(env, "") or settings.value(_ENV_SETTINGS_PREFIX + env, "", type=str)
            checked = str(on).strip().lower() in ("1", "true", "yes", "on")
            cb.setChecked(checked)
            if checked:
                os.environ[env] = "1"
            self._env_flags[env] = cb
            frow.addWidget(cb)
        frow.addStretch(1)
        layout.addLayout(frow)

        btnrow = QHBoxLayout()
        apply_btn = QPushButton("Apply for this session", tab)
        apply_btn.setToolTip("Set these environment variables in the running QGIS so "
                             "the email/notify verbs can use them now")
        apply_btn.clicked.connect(self._apply_env)
        test_ntfy = QPushButton("Send test notification", tab)
        test_ntfy.setToolTip("Apply the fields above, then send a one-off test message "
                             "to your ntfy topic — confirms the server/topic/token work "
                             "before you rely on `notify` in a flow.")
        test_ntfy.clicked.connect(self._test_ntfy)
        test_email = QPushButton("Send test email", tab)
        test_email.setToolTip("Apply the fields above, then send a test email to your "
                              "From address — confirms the SMTP host/port/user/password "
                              "(and TLS) work before `email` is used in a flow.")
        test_email.clicked.connect(self._test_email)
        for b in (apply_btn, test_ntfy, test_email):
            btnrow.addWidget(b)
        btnrow.addStretch(1)
        layout.addLayout(btnrow)

        storerow = QHBoxLayout()
        save_store = QPushButton("Save secrets to QGIS encrypted store", tab)
        save_store.setToolTip("Encrypt the password and token into QGIS's auth database "
                              "(qgis-auth.db, unlocked by your QGIS master password). "
                              "Only a non-secret config ID is kept in settings.")
        save_store.clicked.connect(self._save_secrets_to_authstore)
        load_store = QPushButton("Load secrets from QGIS store", tab)
        load_store.setToolTip("Decrypt the saved password/token from QGIS's encrypted "
                              "store into the fields and apply them (prompts for your "
                              "QGIS master password).")
        load_store.clicked.connect(self._load_secrets_from_authstore)
        for b in (save_store, load_store):
            storerow.addWidget(b)
        storerow.addStretch(1)
        layout.addLayout(storerow)

        self.env_status = QLabel("", tab)
        self.env_status.setWordWrap(True)
        layout.addWidget(self.env_status)

        # --- the environment report ------------------------------------------
        self.setup_view = QTextBrowser(tab)
        self.setup_view.setToolTip(
            "What a launched notebook/flow will actually see: niva version, available "
            "verbs and algorithms, @ connections, and GDAL/PROJ/GEOS/Qt/QGIS versions"
        )
        _recede(self.setup_view)  # a read-only report — blend with the dialog
        layout.addWidget(self.setup_view, 1)

        row = QHBoxLayout()
        refresh = QPushButton("Refresh", tab)
        refresh.setToolTip("Rebuild the environment report above — re-reads the niva "
                           "version, available verbs/algorithms, @ connections and "
                           "library versions as they are right now.")
        refresh.clicked.connect(self._refresh_setup)
        copy = QPushButton("Copy", tab)
        copy.setToolTip("Copy the environment report to the clipboard "
                        "(handy for bug reports)")
        copy.clicked.connect(self._copy_setup)
        row.addWidget(refresh)
        row.addWidget(copy)
        row.addStretch(1)
        layout.addLayout(row)

        self._refresh_setup()
        return tab

    def _browse_log_dir(self):
        chosen = QFileDialog.getExistingDirectory(self, "Run-log folder", self.log_dir.text())
        if chosen:
            self.log_dir.setText(chosen)
            self._on_log_dir_edited()

    def _on_log_enabled(self, value):
        from qgis.core import QgsSettings

        QgsSettings().setValue(_LOG_ENABLED_KEY, value)
        self._update_session_label()

    def _on_log_dir_edited(self):
        from qgis.core import QgsSettings

        QgsSettings().setValue(_LOG_DIR_KEY, self.log_dir.text())
        self._update_session_label()

    def _reset_session_log(self):
        """Start a fresh session log (the next run writes to a new file)."""
        self._session_id = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        self._update_session_label()

    def _session_log_base(self):
        """The session journal base path, or None when logging is disabled."""
        from qgis.core import QgsSettings

        s = QgsSettings()
        if not s.value(_LOG_ENABLED_KEY, True, type=bool):
            return None
        folder = s.value(_LOG_DIR_KEY, default_log_dir(), type=str) or default_log_dir()
        return os.path.join(folder, f"niva-session-{self._session_id}")

    def _update_session_label(self):
        base = self._session_log_base()
        self.session_label.setText((base + ".log") if base else "(logging off)")

    def _refresh_setup(self):
        try:
            report = environment.report_markdown()
        except Exception as exc:  # safety net — never crash the dock
            self.setup_view.setPlainText(f"could not build environment report: {exc}")
            return
        try:
            self.setup_view.setMarkdown(report)  # Qt 5.14+ / Qt6 renders headings & bold
        except (AttributeError, TypeError):  # pragma: no cover — old Qt5
            self.setup_view.setPlainText(report)

    def _copy_setup(self):
        self.setup_view.selectAll()
        self.setup_view.copy()

    def _apply_env(self) -> None:
        """Push the field values into the running QGIS process's environment so the
        email/notify verbs can read them now. Non-secret values are also remembered
        in QgsSettings; secrets are applied for the session only (never persisted)."""
        from qgis.core import QgsSettings

        settings = QgsSettings()
        for env, (le, secret) in self._env_fields.items():
            text = le.text().strip()
            if text:
                os.environ[env] = text
            else:
                os.environ.pop(env, None)
            if not secret:  # remember non-secrets; never write password/token to disk
                settings.setValue(_ENV_SETTINGS_PREFIX + env, text)
        for env, cb in getattr(self, "_env_flags", {}).items():  # boolean alert flags
            on = "1" if cb.isChecked() else ""
            if on:
                os.environ[env] = on
            else:
                os.environ.pop(env, None)
            settings.setValue(_ENV_SETTINGS_PREFIX + env, on)
        self.env_status.setText(
            "Applied for this session. Saved the non-secret fields; the password and "
            "token are kept in memory only (not written to disk)."
        )

    def _test_ntfy(self) -> None:
        self._apply_env()
        try:
            from niva.utilities import send_ntfy

            target = send_ntfy("niva test notification ✔", title="niva")
        except Exception as exc:  # FlowError (no topic) / OpError (network)
            self.env_status.setText(f"ntfy test failed: {exc}")
            return
        self.env_status.setText(f"Sent a test notification to {target}.")

    def _test_email(self) -> None:
        self._apply_env()
        to = os.environ.get("NIVA_SMTP_FROM") or os.environ.get("NIVA_SMTP_USER")
        if not to:
            self.env_status.setText("Set a From address (or SMTP user) first, then test.")
            return
        try:
            from niva.utilities import send_email

            send_email(to=to, subject="niva test email",
                       body="This is a test message sent by niva from the Setup tab.")
        except Exception as exc:
            self.env_status.setText(f"email test failed: {exc}")
            return
        self.env_status.setText(f"Sent a test email to {to}. Check that inbox.")

    # --- encrypted secret storage (QgsAuthManager) ---------------------------

    def _save_secrets_to_authstore(self) -> None:
        """Encrypt the password/token into QGIS's auth DB (qgis-auth.db, AES, unlocked
        by the QGIS master password) and keep only the non-secret config IDs in
        settings. niva never writes the secrets to its own files."""
        from qgis.core import QgsApplication, QgsAuthMethodConfig, QgsSettings

        am = QgsApplication.authManager()
        # storing prompts QGIS to set/enter the master password if needed
        if hasattr(am, "setMasterPassword") and not am.masterPasswordIsSet():
            if not am.setMasterPassword(True):
                self.env_status.setText("Master password not set — secrets not saved.")
                return
        settings = QgsSettings()
        smtp_pw = self._env_fields["NIVA_SMTP_PASSWORD"][0].text().strip()
        smtp_user = self._env_fields["NIVA_SMTP_USER"][0].text().strip()
        ntfy_tok = self._env_fields["NIVA_NTFY_TOKEN"][0].text().strip()
        saved = []
        if smtp_pw:
            cfg = QgsAuthMethodConfig()
            cfg.setName("niva SMTP")
            cfg.setMethod("Basic")
            cfg.setConfig("username", smtp_user)
            cfg.setConfig("password", smtp_pw)
            if am.storeAuthenticationConfig(cfg) and cfg.id():
                settings.setValue(_SMTP_AUTHCFG_KEY, cfg.id())
                saved.append("SMTP password")
        if ntfy_tok:
            cfg = QgsAuthMethodConfig()
            cfg.setName("niva ntfy")
            cfg.setMethod("Basic")
            cfg.setConfig("password", ntfy_tok)
            if am.storeAuthenticationConfig(cfg) and cfg.id():
                settings.setValue(_NTFY_AUTHCFG_KEY, cfg.id())
                saved.append("ntfy token")
        self.env_status.setText(
            ("Saved to QGIS encrypted store: " + ", ".join(saved) +
             ". Use 'Load secrets from QGIS store' after a restart.")
            if saved else "Nothing to save — enter a password or token first."
        )

    def _load_secrets_from_authstore(self) -> None:
        """Decrypt the saved secrets from QGIS's store into the fields + environment
        (prompts for the QGIS master password)."""
        from qgis.core import QgsApplication, QgsAuthMethodConfig, QgsSettings

        am = QgsApplication.authManager()
        settings = QgsSettings()
        loaded = []

        def fetch(authcfg_id):
            cfg = QgsAuthMethodConfig()
            am.loadAuthenticationConfig(authcfg_id, cfg, True)  # full=True → secrets
            return cfg

        smtp_id = settings.value(_SMTP_AUTHCFG_KEY, "", type=str)
        if smtp_id:
            cfg = fetch(smtp_id)
            pw = cfg.config("password")
            if pw:
                self._env_fields["NIVA_SMTP_PASSWORD"][0].setText(pw)
                user = cfg.config("username")
                if user and not self._env_fields["NIVA_SMTP_USER"][0].text().strip():
                    self._env_fields["NIVA_SMTP_USER"][0].setText(user)
                loaded.append("SMTP password")
        ntfy_id = settings.value(_NTFY_AUTHCFG_KEY, "", type=str)
        if ntfy_id:
            tok = fetch(ntfy_id).config("password")
            if tok:
                self._env_fields["NIVA_NTFY_TOKEN"][0].setText(tok)
                loaded.append("ntfy token")
        if loaded:
            self._apply_env()  # push the loaded secrets (and fields) into the environment
            self.env_status.setText("Loaded from QGIS encrypted store and applied: "
                                    + ", ".join(loaded) + ".")
        else:
            self.env_status.setText("No saved secrets found (or master password "
                                    "not entered). Save them first.")

    # --- actions -------------------------------------------------------------

    def _open(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open a .niva flow", "", "niva flows (*.niva);;All files (*)"
        )
        if not path:
            return
        try:
            with open(path, encoding="utf-8") as fh:
                self.editor.setPlainText(fh.read())
        except OSError as exc:
            self._log(f"could not open {path}: {exc}")
            return
        self.path = path
        self.path_label.setText(os.path.basename(path))

    # --- Convert tab: .niva <-> PyQGIS --------------------------------------

    def _export_to_py(self):
        from niva.transpile import export_script

        text = self.editor.toPlainText()
        src = os.path.basename(self.path) if self.path else "<flow>"
        try:
            py = export_script(text, source_name=src, out_name="flow.py")
        except Exception as exc:  # FlowError (parse/bind) — show, don't crash
            self.convert_status.setText(f"Export failed: {exc}")
            return
        self.convert_view.setPlainText(py)
        self._last_export = py
        self._convert_mode = "py"
        self.send_to_flow_btn.setEnabled(False)
        steps = py.count("processing.run(")
        self.convert_status.setText(
            f"Exported {steps} processing.run step(s). Edit here if you like, then "
            "Save .py… or Import .py… to round-trip it back to a flow."
        )

    def _save_py(self):
        py = self.convert_view.toPlainText()
        if not py.strip():
            self.convert_status.setText("Nothing to save — Export a flow first.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Save PyQGIS script", "flow.py", "Python (*.py);;All files (*)"
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(py)
        except OSError as exc:
            self.convert_status.setText(f"Could not save: {exc}")
            return
        self.convert_status.setText(f"Saved {os.path.basename(path)}.")

    def _import_from_py(self):
        from niva.transpile import import_script

        # If the preview is holding a (possibly hand-edited) .py, import that;
        # otherwise open a .py file to import.
        if getattr(self, "_convert_mode", None) == "py" and self.convert_view.toPlainText().strip():
            py = self.convert_view.toPlainText()
            origin = "the script shown above"
        else:
            path, _ = QFileDialog.getOpenFileName(
                self, "Import a PyQGIS script", "", "Python (*.py);;All files (*)"
            )
            if not path:
                return
            try:
                with open(path, encoding="utf-8") as fh:
                    py = fh.read()
            except OSError as exc:
                self.convert_status.setText(f"Could not open: {exc}")
                return
            origin = os.path.basename(path)

        niva, warnings = import_script(py)
        if not niva.strip():
            self.convert_status.setText(
                f"No importable processing.run(…) calls in {origin}. "
                + (" ".join(warnings) if warnings else "")
            )
            self.send_to_flow_btn.setEnabled(False)
            return
        self.convert_view.setPlainText(niva)
        self._last_import = niva
        self._convert_mode = "niva"
        self.send_to_flow_btn.setEnabled(True)
        msg = f"Imported {origin} → flow ({niva.strip().count(chr(10)) + 1} stage(s))."
        if warnings:
            msg += "  ⚠ " + "  ".join(warnings)
        self.convert_status.setText(msg)

    def _send_to_flow(self):
        niva = self._last_import or self.convert_view.toPlainText()
        if not niva.strip():
            return
        self.editor.setPlainText(niva)
        self.path = None
        self.path_label.setText("(imported flow)")
        self.tabs.setCurrentIndex(0)  # jump to the Flow tab

    def _run(self):
        self._execute(dry_run=False)

    def _dry_run(self):
        self._execute(dry_run=True)

    def _clear(self):
        self.output.clear()

    def _cancel(self):
        task = getattr(self, "_task", None)
        if task is not None:
            task.cancel()
            self._log("  stopping…")

    def _execute(self, *, dry_run: bool):
        if getattr(self, "_running", False):  # one flow at a time (Oscar A9)
            return
        text = self.editor.toPlainText()

        if dry_run:  # fast + mock — run synchronously, no background task
            self._log("$ niva --dry-run")
            try:
                result = runner.run_flow(text, file=self.path, dry_run=True)
            except Exception as exc:  # safety net — never let the dock crash QGIS
                self._log(f"niva: unexpected error: {exc}")
                return
            self._show_result(result)
            return

        # Push the Setup-tab email/notify config into the environment first, so a
        # `notify`/`email` step in the flow uses the same server/topic/token as the
        # Setup tab's "Send test" buttons (the worker thread shares this process env).
        self._apply_env()

        # A real run goes to a background QgsTask so the QGIS UI stays responsive.
        from qgis.core import QgsApplication

        from .flowtask import NivaFlowTask

        self._running = True
        self.run_btn.setEnabled(False)
        self.dry_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self._log("$ niva run")
        self._task = NivaFlowTask(text, self.path, self._session_log_base())
        self._task.message.connect(self._on_progress)
        self._task.taskCompleted.connect(self._on_task_finished)
        self._task.taskTerminated.connect(self._on_task_finished)
        QgsApplication.taskManager().addTask(self._task)

    def _on_task_finished(self):
        """Runs on the main thread when the background flow ends — safe to touch the map."""
        task = getattr(self, "_task", None)
        self._running = False
        self._task = None
        self.run_btn.setEnabled(True)
        self.dry_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        if task is None or task.result is None:
            self._log("niva: run produced no result")
            return
        self._show_result(task.result)

    def _show_result(self, result: dict):
        if result["ok"]:
            self._log(result["summary"])
            if result.get("layer") is not None:
                self._add_to_map(result["layer"])
        else:
            self._log(f"niva: {result['error']}")
        if result.get("elapsed") is not None:
            self._log(f"  ({_fmt_secs(result['elapsed'])})")
        if result.get("log"):
            self._log(f"  log: {result['log']}")

    def _on_progress(self, message: str):
        # Delivered on the main thread via the task's queued signal — safe to update.
        self.output.appendPlainText(message)

    # --- map integration -----------------------------------------------------

    def _add_to_map(self, layer):
        """Add the flow's final layer to the project so results land on the map."""
        from qgis.core import QgsProject, QgsRasterLayer, QgsVectorLayer

        ref = getattr(layer, "ref", None)
        added = None
        if isinstance(ref, str):  # a saved file path
            name = os.path.splitext(os.path.basename(ref))[0]
            vec = QgsVectorLayer(ref, name, "ogr")
            added = vec if vec.isValid() else QgsRasterLayer(ref, name)
        elif ref is not None and getattr(ref, "isValid", lambda: False)():
            added = ref
        if added is not None and added.isValid():
            QgsProject.instance().addMapLayer(added)
            self._log(f"  added to map: {added.name()}")

    def _log(self, message: str):
        self.output.appendPlainText(message)


def _fmt_secs(seconds: float) -> str:
    if seconds < 1:
        return f"{round(seconds * 1000)} ms"
    if seconds < 60:
        return f"{seconds:.1f} s"
    m, s = divmod(int(seconds), 60)
    return f"{m}m {s:02d}s"


def _mono() -> QFont:
    font = QFont("monospace")
    try:
        font.setStyleHint(QFont.StyleHint.Monospace)  # Qt6 (QGIS 4)
    except AttributeError:  # pragma: no cover — Qt5 (QGIS 3)
        font.setStyleHint(QFont.Monospace)
    return font


def _section_label(text: str, parent) -> QLabel:
    """A bold section heading for the Setup tab."""
    lbl = QLabel(f"<b>{text}</b>", parent)
    lbl.setContentsMargins(0, 8, 0, 0)
    return lbl


def _recede(widget) -> None:
    """Make a read-only text widget blend with the dialog: paint its background with
    the window colour instead of the editable-field (Base) colour. Theme-adaptive —
    works on light and dark themes — so only the editor reads as an input."""
    try:
        base, window = QPalette.ColorRole.Base, QPalette.ColorRole.Window  # Qt6
    except AttributeError:  # pragma: no cover — Qt5
        base, window = QPalette.Base, QPalette.Window
    palette = widget.palette()
    palette.setColor(base, palette.color(window))
    widget.setPalette(palette)
