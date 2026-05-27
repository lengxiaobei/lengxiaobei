# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Common commands

Install development dependencies:

```bash
make setup
```

Run the backend API gateway on `127.0.0.1:8000`:

```bash
make backend
```

Run the frontend dev server on `127.0.0.1:5173`:

```bash
make frontend
```

Run the frontend only through npm:

```bash
npm run dev --prefix frontend
```

Build the frontend:

```bash
npm run build --prefix frontend
```

Run the repository test command:

```bash
make test
```

Run a single backend test file:

```bash
python3 -m pytest backend/tests/test_memory_tree.py -q
```

Run a single backend test by name:

```bash
python3 -m pytest backend/tests/test_memory_tree.py::test_name -q
```

Run backend compile and frontend type/build checks:

```bash
make check
```

Synchronize configured external services into memory:

```bash
make sync
```

Clean generated caches and frontend build output:

```bash
make clean-generated
```

Docker Compose starts the backend and Redis, but not the frontend dev server:

```bash
docker compose up -d
```

## Environment and local services

Copy `.env.example` to `.env` before running locally. The backend reads the root `.env` through `backend/config.py`. Key local defaults are `BACKEND_HOST=127.0.0.1`, `BACKEND_PORT=8000`, `BACKEND_CORS_ORIGINS=http://127.0.0.1:5173,http://localhost:5173`, `DATA_DIR=data`, and `DATABASE_URL=sqlite:///data/sqlite/agent.db`.

The frontend is a Vite app in `frontend/`. `frontend/vite.config.ts` binds the dev server to `127.0.0.1:5173` and proxies `/api` requests to `http://127.0.0.1:8000`. Frontend code also supports `VITE_API_BASE` and `VITE_WS_URL`; when those are unset, HTTP calls use relative `/api/...` paths through the Vite proxy and WebSocket calls default to `ws://127.0.0.1:8000/ws`.

If the UI shows `连接失败：Failed to fetch`, first verify both local services are running: the frontend at `http://127.0.0.1:5173` and the backend health endpoint at `http://127.0.0.1:8000/api/health`. The chat send path is `frontend/src/stores/chatStore.ts`, which posts to `/api/conversations`; the backend route is `backend/api/routes/conversations.py`.

## High-level architecture

LengXiaobei is a local-first autonomous agent system inspired by OpenClaw, Hermes, and OpenHuman. The React console talks to a FastAPI gateway. The gateway builds a shared runtime that wires together conversation planning, tool dispatch, memory, synchronization, skill evolution, local agent integrations, and background scheduling.

The canonical backend entrypoint is `backend/main.py`, which exposes `backend.gateway.server:create_app()`. `backend/gateway/server.py` creates the FastAPI app, installs CORS from settings, mounts all `/api/*` routers, starts/stops the runtime scheduler, and exposes `/ws` for realtime gateway messages.

Runtime composition happens in `backend/core/runtime_factory.py`. It constructs the SQLite-backed memory tree, vector store, graph store, sync manager, skill store, local agent hub, tool registry, dispatcher, reflector, autonomy engine, scheduler, and commander, then packages them into a `RuntimeContext`.

The main conversation flow is: frontend chat store posts a message to `/api/conversations`; `backend/api/routes/conversations.py` calls `RuntimeContext.commander.handle_message`; `backend/core/commander.py` records the user message into memory, recalls related memory, builds a lightweight rule-based plan, optionally dispatches a tool through `backend/core/dispatcher.py`, or falls back to the configured LLM adapter; then it writes the assistant response back to memory and returns it to the frontend.

The tool layer is centered on `backend/tools/registry.py` and `backend/core/dispatcher.py`. Built-in tools live under `backend/tools/builtin/` for filesystem, shell, web, browser, and local/controlled agent operations. Dynamic or generated skills are stored under `data/skills` and indexed by `backend/evolution/skill_store.py`.

The memory layer uses `backend/memory/sqlite_backend.py` as primary persistence under `data/sqlite/agent.db`. `backend/memory/tree.py` provides structured long-term memory, `backend/memory/vector_store.py` provides semantic-ish retrieval with local fallback behavior, `backend/memory/graph_store.py` stores relationships, and `backend/memory/sync/` handles external-source synchronization.

The evolution and autonomy layers are separate from the core request path. `backend/evolution/reflector.py`, `skill_gen.py`, `evaluator.py`, and `skill_store.py` implement reflection, draft skill generation, evaluation, and storage. `backend/autonomy/` implements goal selection, auditing, learning, evolution, and periodic autonomous execution. The scheduler configured in `runtime_factory.py` periodically runs memory reindexing, reflection, and autonomy ticks.

The frontend is a React 18 + TypeScript + Zustand app under `frontend/src`. `frontend/src/App.tsx` switches between major console tabs using `systemStore.activeTab`; tab pages live in `frontend/src/pages/`. State is mostly colocated in Zustand stores under `frontend/src/stores/`, while API helpers and WebSocket setup live under `frontend/src/api/`.
