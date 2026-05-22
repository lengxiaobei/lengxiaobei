"""lx_web — Flask 应用工厂

将原 lx_web.py 单文件拆分为 Blueprint 架构：
  shared/     — 共享状态、工具函数、SSE 基础设施、中间件
  blueprints/ — 7 个 Blueprint (system, chat, evolution, learning, autonomy, memory, sse)
"""

import os
import sys
from pathlib import Path

# 确保项目根目录在 sys.path 中
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from flask import Flask


def create_app() -> Flask:
    """创建并配置 Flask 应用，注册所有 Blueprint。"""
    app = Flask(__name__)

    # ---------- 中间件 ----------
    from lx_web.shared.middleware import _add_cors_headers, _handle_options
    app.after_request(_add_cors_headers)
    app.before_request(_handle_options)

    # ---------- 注册 Blueprint ----------
    # 注意：system_bp 包含 / 和 /<path:path> catch-all，必须最后注册
    from lx_web.blueprints.sse import sse_bp
    from lx_web.blueprints.chat import chat_bp
    from lx_web.blueprints.evolution import evolution_bp
    from lx_web.blueprints.learning import learning_bp
    from lx_web.blueprints.autonomy import autonomy_bp
    from lx_web.blueprints.memory import memory_bp
    from lx_web.blueprints.system import system_bp

    app.register_blueprint(sse_bp)
    app.register_blueprint(chat_bp)
    app.register_blueprint(evolution_bp)
    app.register_blueprint(learning_bp)
    app.register_blueprint(autonomy_bp)
    app.register_blueprint(memory_bp)
    # system_bp 最后注册（包含 catch-all 路由）
    app.register_blueprint(system_bp)

    return app


def main():
    """CLI 入口。"""
    app = create_app()
    host = os.environ.get("LX_WEB_HOST", "0.0.0.0")
    port = int(os.environ.get("LX_WEB_PORT", "8088"))
    debug = os.environ.get("LX_DEBUG", "0") == "1"
    print(f"冷小北 Web 启动: http://{host}:{port}")
    app.run(host=host, port=port, debug=debug, threaded=True)


if __name__ == "__main__":
    main()
