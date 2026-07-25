# KineticSketch Engineering Audit Report

**Audit date:** July 20, 2026

**Scope:** Current local working tree

**Status:** Local engineering and single-container checks passed; full-stack staging remains

## 1. Purpose and limits

This report details the comprehensive security, architectural, and functional checks performed on the KineticSketch deployment. These controls verify technical integrity and loadability, though they do not claim independent clinical validation, standalone scientific accuracy without a trained checkpoint, or general enterprise scalability guarantees.

## 2. Verified commands and results

The final local checks were run from the repository root.

| Check | Command | Result |
|---|---|---|
| Automated tests | `.venv/bin/python -m pytest -q --disable-warnings` | 23 passed |
| Python lint | `ruff check app tests scripts/build_drug_db.py serve.py run.py app.py wsgi.py compose_up.py` | Passed |
| Static typing | `mypy app` | Passed; no issues in 23 source files |
| JavaScript syntax | `node --check app/static/sketch.js` and `node --check app/static/interaction_viewer.js` | Passed |
| Patch whitespace | `git diff --check` | Passed |
| Python security scan | `bandit -q -r app` | Passed with no reported findings |
| Compose syntax | Parsed with PyYAML safe loader, including anchors | Passed |
| Production WSGI smoke test | `serve.py` from `/tmp`, then all health endpoints | Passed |
| Production image build | `podman build --tag kineticsketch:production-smoke .` | Passed |
| Hardened container runtime | Read-only root, non-root user, all capabilities dropped, dynamic host port | Readiness passed |

The production Docker image builds successfully from the locked Python 3.11 dependency set. The container runtime enforces a read-only root filesystem, drops unnecessary capabilities, utilizes `no-new-privileges`, mounts writable runtime-only volumes, and automatically assigns a loopback host port. Subsequent requests to `/health/ready` reliably return HTTP 200 with database, model checkpoint, drug-data, and storage checks fully passing.

## 3. Functional and isolation checks

The automated tests and code review cover:

- public UI and JavaScript assets are present and non-empty;
- protected API routes reject unauthenticated requests;
- registration, login, session lookup, and logout;
- per-user and per-job output directories;
- authenticated SDF download;
- static routes do not expose generated workspace files;
- UUID/path-traversal rejection;
- task status and cancellation ownership;
- invalid PDB rejection;
- compressed-upload decompression and record limits;
- login rate limiting;
- model checkpoint loading and prediction;
- fail-closed missing-checkpoint and checksum-mismatch behavior;
- browser-contract flow from authentication through analysis, task submission, status, and download;
- liveness and dependency-aware readiness behavior;
- dynamic port selection and explicit provider-port preservation;
- project-root path resolution independent of the current working directory;
- model-digest readiness verification;
- nested task-parameter validation; and
- uploaded-filename response sanitization; and
- allow-listed iframe embedding and partitioned embedded-session cookies.

Generated structures are stored under:

```text
jobs/<user-id>/<job-id>/
  input/
  scratch/
  outputs/
```

Job and user identifiers are validated as UUIDs. Resolved paths are constrained to the owning user's job directory. Generated files are downloaded only through the authenticated allow-listed endpoint.

## 4. Authentication and web security

Implemented controls include:

- mandatory `FLASK_SECRET_KEY` of at least 32 characters;
- `HttpOnly`, default `SameSite=Lax`, and production `Secure` session cookies;
- explicit allow-listed embedding with Secure, `SameSite=None`, partitioned
  cookies when embedded mode is enabled;
- eight-hour permanent-session lifetime after login;
- Redis-backed production login rate limiting;
- twelve-character minimum passwords and restricted usernames;
- PBKDF2-HMAC password storage with random salts;
- constant-time password-hash comparison;
- HSTS in production;
- Content Security Policy;
- CSP frame-ancestor allow-listing, MIME-sniffing, and referrer-policy headers;
- task ownership checks; and
- no client-selected server filesystem paths for docking.

## 5. Model loading and scientific status

The model loader:

- uses `MODEL_DEVICE=cpu` by default;
- supports explicitly configured `cuda` or `auto` modes;
- verifies the checkpoint SHA-256 digest;
- uses `torch.load(..., weights_only=True)`;
- fails closed for missing, corrupt, or incompatible weights; and
- performs a deterministic startup shape/type check.

These controls verify technical integrity and loadability. They do not prove predictive accuracy. Claims about RMSF, SASA, B-factor, charge, or HOMO-LUMO-gap performance still require documented training provenance, target definitions and units, held-out metrics, baselines, uncertainty, and applicability-domain analysis.

The MD workflow is a task-orchestration demonstration. It does not perform physical molecular dynamics and must not be presented as such. OPLS-AA is disabled; supported minimization choices are MMFF94, MMFF94s, and UFF.

## 6. Upload, storage, and cleanup controls

PDB uploads are stored in the authenticated job directory and enforce:

- request-size checks;
- a 10 MB decompressed limit;
- a maximum of 100,000 records;
- a maximum of 50,000 atoms;
- `.pdb`, `.ent`, and `.pdb.gz` handling;
- basic PDB-record validation; and
- opaque client references instead of absolute server paths.

Celery Beat schedules hourly cleanup. The cleanup task removes only expired,
UUID-shaped job directories contained by the configured jobs root. It retains
recently modified jobs and reports deleted jobs and reclaimed bytes. Per-user
quotas and a low-free-disk admission control remain future operational work.

Runtime jobs, uploads, user databases, action logs, generated molecules, profiling output, and repository-analysis exports are excluded from Git and the production image where appropriate.
