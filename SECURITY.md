# Security Policy

## Reporting a vulnerability

Please report security issues **privately** — do not open a public issue for an
unfixed vulnerability.

- Preferred: open a [GitHub private vulnerability report](https://github.com/johnzastrow/niva/security/advisories/new)
  (Security → Report a vulnerability).
- Or email the maintainer at the address on the GitHub profile.

We aim to acknowledge a report within a few days and will coordinate a fix and
disclosure timeline with you.

## Supported versions

niva is pre-1.0 and ships fixes on the latest minor release. Please reproduce on
the most recent release before reporting.

## Security posture (what reduces risk by design)

- **Zero runtime dependencies** — niva imports only the Python standard library and
  the QGIS APIs already present in your QGIS install. There is no third-party package
  tree to compromise.
- **No dynamic code execution** of input — niva never `eval`/`exec`/`pickle`s a flow or
  a file. The `import` command parses foreign PyQGIS scripts with `ast.parse` (static
  analysis only; the script is never executed).
- **Credentials stay in QGIS / the environment** — database and notification secrets
  are read from the QGIS connection store or environment variables, never from flow
  text, and are never written to logs or the run journal.
- **Network access is constrained** — remote `show` fetches only `http(s)` URLs
  (scheme allowlist), validates TLS, and refuses XML carrying a `<!DOCTYPE>` (XXE guard).

## For contributors

- Commits to `main` go through pull requests with required CI; force-pushes and
  branch deletion are disallowed.
- GitHub Actions are pinned to commit SHAs and updated via Dependabot.
- Never commit secrets. Run the staged-content scan in `~/.claude/CLAUDE.md` /
  rely on GitHub push protection before pushing.
