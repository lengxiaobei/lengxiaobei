# Directory Rules

This project must stay small enough for humans and agents to reason about. The rule is simple:
new directories need a clear owner, lifecycle, and import/runtime boundary.

## Canonical Top-Level Directories

```text
config/                    runtime configuration
deploy/                    launchd, compose, prometheus, service files
docs/                      architecture, product, and operating documents
lx_web/                    Python Gateway/backend
src/                       importable Python Agent runtime
tests/                     tests
scripts/                   operator and maintenance scripts
memory/                    runtime memory, lessons, runs, local databases
state/                     runtime state, locks, event journals
logs/                      local logs, ignored by git
prompts/                   prompt/personality documents
skills/                    managed skill documents
bridges/                   optional language bridges
memory_layer/              optional Rust memory layer
trae-plugin-lengxiaobei/   optional Trae integration package
```

## Future Frontend Directory

Use `frontend/` only when the embedded Web UI is moved into a real client application. Until then,
do not create parallel `web/`, `ui/`, `client/`, or `dashboard/` directories.

## Legacy Top-Level Runtime Directories

These directories currently exist because earlier versions stored runtime data at the repository
root:

```text
assessment/
buddy/
goals/
integrity/
learning/
motivation/
permissions/
```

Do not create new files there unless maintaining compatibility with existing code. New runtime data
should go under `memory/` or `state/`; new importable logic should go under `src/`.

## Forbidden Generated Directories

These must not be committed and should be deleted when found:

```text
__pycache__/
.pytest_cache/
.ruff_cache/
*.egg-info/
build/
dist/
node_modules/
target/
```

The layout guard checks for these. If a tool needs them locally, they remain ignored and disposable.

## File Placement Rules For Agents

- Python package code: `src/` or `lx_web/`.
- Web API routes: `lx_web/blueprints/`.
- Shared Web helpers/state: `lx_web/shared/`.
- Runtime JSON/log/database files: `memory/`, `state/`, or `logs/`.
- Service/deployment files: `deploy/`.
- Shell/operator scripts: `scripts/`.
- Design docs and operating notes: `docs/`.
- Prompt/personality files: `prompts/`.
- Cross-language bridge code: `bridges/<language>/`.
- Tests: `tests/`.

Before creating a new top-level directory, update this document and
`scripts/check_project_layout.py` in the same change.

