# LengXiaobei Architecture

This document is the source of truth for the product architecture. Keep it in sync with
`README.md`, `docs/AGENTS.md`, `CLAUDE.md`, and the executable layout guard in
`scripts/check_project_layout.py`.

## Reference From OpenClaw

OpenClaw's useful pattern is not its exact technology stack. The parts worth copying are:

- A single long-lived Gateway owns the control plane, events, health, and client protocol.
- Frontends are clients of the Gateway, not alternate backends.
- One effective port/bind/auth path is used for HTTP, WebSocket, UI, and operator APIs.
- Configuration is schema validated and hot-reloaded only when safe.
- Tools, sandboxing, and write permissions are policy-driven, not left to prompt wording.
- `doctor` is an operator command, not just a test helper.

LengXiaobei should follow that shape while staying Python-first.

## Target Runtime Shape

```text
Operator / Browser / future Desktop UI
        |
        v
lx_web Gateway
  - HTTP API
  - SSE or future WebSocket event stream
  - status, health, restart, config, memory, autonomy APIs
        |
        v
src.core.LengXiaobei
  - MemoryFacade
  - ReasoningFacade
  - EvolutionFacade
  - GuardianFacade
        |
        v
runtime data under memory/, state/, logs/
```

## Gateway Rules

- Canonical Web entry: `python3 -m lx_web.app`.
- Compatibility entry: `python3 lx_web.py`, but it must remain a thin wrapper.
- Web host variable: `LX_WEB_HOST`.
- Web port variable: `LX_WEB_PORT`.
- Do not introduce `LX_PORT`, `WEB_PORT`, `FLASK_RUN_PORT`, or another runtime port alias.
- The Gateway owns health, status, events, and API routing. Feature modules register through
  blueprints and must not start their own web servers.

## Frontend/Backend Boundary

Current state:

- Backend package: `lx_web/`
- UI: embedded HTML in `lx_web.blueprints.system`
- Event stream: `/api/events` over SSE

Target state:

```text
frontend/                 # future standalone UI client
  package.json
  src/
  public/
  dist/                   # ignored build output

lx_web/                   # Python Gateway/backend
  app.py
  blueprints/
  shared/
```

Rules:

- Frontend code must not import Python internals.
- Backend code must not contain large UI strings once `frontend/` exists.
- The frontend talks to the Gateway only through documented HTTP/SSE or future WebSocket APIs.
- Generated frontend artifacts (`dist/`, `node_modules/`) must never be committed.

## Agent Runtime Boundary

`src/` is the only place for importable Python Agent code. New runtime capabilities must fit one
of these buckets before a new module is created:

- core orchestration: `src/core.py`
- facade boundary: `src/facade_*.py`
- memory: `src/*memory*.py` or `src/memory/`
- evolution: `src/evolution/` or `src/self_evolution.py`
- safety/permissions: `src/hard_boundary.py`, `src/permission.py`, `src/evolution_permission.py`
- operations: `src/doctor.py`, `src/health_check.py`, `src/monitoring.py`
- tools/integrations: `src/tool_registry.py`, `src/integration.py`, `bridges/`

Do not create new top-level source folders for a single capability.

## Self-Evolution Boundary

Self-evolution may only modify files listed in `SAFE_TARGETS`, and that list must contain only
real, importable, low-coupling files. A function that exists and is callable is not enough to claim
semantic success. Quality reporting must keep these stages separate:

- `syntax_ok`
- `function_exists`
- `callable_ok`
- `semantic_ok`
- `integrated_ok`

Fallback-generated code should be reported as degraded until a real workflow proves value.

