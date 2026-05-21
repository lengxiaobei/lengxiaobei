# control_layer — LEGACY (Rust)

> **已废弃** — 此 Rust control_layer 已被 Python `src/core.py` 替代。

原功能：守护 Python 进程、提供 `/api/status`、转发记忆写入。

迁移至: `src/core.py` + `src/facade_guardian.py` + `src/health_check.py`

保留原因: 历史参考、未来可能的 Rust 桥接实验。
如无维护者，可归档至 `docs/archived/`。
