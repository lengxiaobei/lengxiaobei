# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Common commands

Set up a local environment with:

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Run the Blueprint-based Web app with:

```bash
LX_WEB_PORT=8088 python3 -m lx_web.app
```

`python3 lx_web.py` is supported only as a compatibility wrapper and should start the same `lx_web.app:create_app()` application. Use `LX_WEB_PORT` for the Web port and `LX_WEB_HOST` for the bind host; do not introduce a second port variable.

Run the core agent and daemon with:

```bash
python3 -m src.core
python3 daemon.py
```

Run tests and focused checks with:

```bash
pytest tests/ -q
pytest tests/test_core_modules.py -q
pytest tests/test_integration_web.py -v -s
pytest tests/test_integration_web.py::TestSystemModule::test_runtime_status -v -s
python3 -m compileall -q src lx_web
ruff check src/ tests/ --select E9,F63,F7,F82
```

Docker starts the Web app on container port 8088:

```bash
LX_WEB_PORT=8088 docker compose up --build
```

## Architecture overview

The core runtime is `src.core.LengXiaobei`, which lazily coordinates four Facades: `facade_memory.py`, `facade_reasoning.py`, `facade_evolution.py`, and `facade_guardian.py`. The surrounding modules implement memory, query/tool routing, self-evolution, safety checks, budget/health, and KAIROS events.

The Web backend’s canonical entrypoint is `lx_web.app:create_app()`. `lx_web.py` must remain a thin compatibility wrapper only. The Flask app is split into Blueprints under `lx_web/blueprints/`: system routes, chat, evolution, learning, autonomy, memory, and SSE. Shared Web state, middleware, restart helpers, and SSE fanout live under `lx_web/shared/`.

Self-evolution is centered in `src/self_evolution.py`. Lessons come from `src/agent_learning.py`; source edits are constrained to real, importable `SAFE_TARGETS`, currently `src/learned_capabilities.py`, `src/active_learner.py`, `src/goal_system.py`, `src/critic.py`, `src/code_change_log.py`, and `src/testing.py`. Do not point prompts or fallback logic at deleted modules such as `src/buddy.py` or `src/dev_team.py`.

A self-evolution run chooses a target, builds `expected_functions`, applies either the evolution engine or a deterministic fallback, runs `compileall` and `tests/test_core_modules.py`, then verifies the declared functions through AST/import/callable checks. Treat quality as staged signals: `syntax_ok`, `function_exists`, `callable_ok`, `semantic_ok`, and `integrated_ok`. A callable function is not proof that the business workflow integrated or semantically benefited from the change.

Runtime state and audit data are persisted mostly under `memory/`, including lessons, self-evolution runs, autonomy runs, reflection logs, and code-change logs. These files are runtime data, not static source architecture.

Packaging is defined in `pyproject.toml`. If new importable packages are added, update the setuptools package list so installed/containerized runs match local source runs.
