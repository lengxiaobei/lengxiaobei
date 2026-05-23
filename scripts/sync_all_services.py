#!/usr/bin/env python3
"""Manually trigger all configured sync connectors."""

from __future__ import annotations

import asyncio

from backend.core.runtime_factory import build_runtime


async def main() -> int:
    runtime = build_runtime(logger_name="scripts.sync")
    connector_names = sorted(runtime.sync_manager.connectors.keys())
    if not connector_names:
        print("No sync services are configured. Use /api/memory/sync/import or register connectors first.")
        return 0
    for service in connector_names:
        print(f"Syncing {service}...")
        print(await runtime.sync_manager.run_once(service))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
