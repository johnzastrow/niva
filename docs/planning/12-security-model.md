# Niva — Security & Threat Model (v1)

_What niva trusts, what it validates, and the safe defaults. Closes Oscar **G9**;
addresses the C5 / U5 risks._

---

## 1. Trust model

- **A `.niva` flow is code-equivalent.** Running one executes algorithms, SQL, and
  file reads/writes **with the running user's privileges**. Treat a flow from an
  untrusted source exactly like a shell script. niva does **not** sandbox.
- **niva runs locally.** It executes on the user's machine against their files and
  their QGIS-configured connections. There is **no niva server and no telemetry**
  in v1 — nothing is phoned home.

## 2. Threats & controls

| Threat | Control |
|--------|---------|
| **Running an untrusted `.niva`** (sent by email, copied from the web) | Documented as code-equivalent; **`--dry-run` previews every resolved call** before running; no auto-run of files; (future) signing if a service mode appears. |
| **SQL injection** via the `sql` verb | niva passes the user's SQL **verbatim** and **never builds SQL by string-interpolating values**. Identifiers/connection names that *niva* adds are validated/parameterized. The user's own SQL is their responsibility — same as any DB client. |
| **Arbitrary algorithm** via `run id KEY=value` | `run` executes any installed algorithm at PyQGIS privilege — an intentional escape hatch, documented as such (`07-§8`). No privilege escalation beyond what PyQGIS already grants. |
| **Credential exposure** | Database logins live in **QGIS's connection store**, referenced only by `@name` (`02-§3.5`). niva **never stores, logs, or transmits credentials**; the op-log and lineage **redact** connection secrets/tokens. |
| **Path traversal / surprise writes** | `save` writes only where told (user privilege); the **input-overwrite guard** (`03-§2.5`) blocks clobbering a source read earlier in the same flow; the only writes are declared outputs + the managed temp dir. |
| **Package install (the plugin)** | The plugin installs **only the `niva` package**, via the validated installer (`marimo-qgis` pattern); package names are allowlist-validated; no arbitrary post-install code. niva itself keeps **near-zero, pure-Python deps** so it can't drag in a compromised binary that also breaks QGIS (Oscar E1). |
| **Malformed/hostile input data** | Parsing bad geodata is GDAL/QGIS's attack surface; niva adds `assess`/`fix` but **inherits** their parser risk and cannot fully shield against it. |
| **Log/journal as a leak** | The journal records params and algorithm ids; it **must redact** secrets and may contain file paths — treat journals as you would any build log. |

## 3. Safe defaults (security-relevant)

- **No silent overwrite of an input** (`03-§2.5`).
- **No silent reprojection**, and **no silent degree-buffers** (`03-§1.1/§1.2`) —
  preventing *wrong* output, which for analysis is its own kind of failure.
- **Secrets redacted** in logs/lineage.
- **Everything inspectable before it runs** — `--dry-run` and `describe`.
- **Minimal dependency surface** — fewer packages = smaller supply-chain risk and
  less chance of breaking QGIS's Python (E1).

## 4. Out of scope (v1)

Sandboxing flows, multi-user / RBAC, and signing `.niva` files are **not** in v1 —
niva is a single-user, local tool. **Revisit when a service / daemon mode (v2.x)
runs *other people's* flows**, which changes the trust boundary entirely (then:
sandboxing, authn/authz, resource limits, and signed flows become required).
