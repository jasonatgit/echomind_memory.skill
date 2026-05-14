#!/usr/bin/env python3
# EchoMind Memory — 统一入口
# 
# HTTP 模式 (默认): python3 main.py
#   启动 FastAPI 服务，供 OpenClaw / OpenCode / Claude Code 通过 HTTP 调用
#
# MCP 模式: python3 main.py --mcp  
#   启动 MCP stdio 服务，供支持 MCP 的工具自动启动（未来实现）

import sys
import os

# 确保项目根目录在 sys.path
_pkg_dir = os.path.dirname(os.path.abspath(__file__))
if _pkg_dir not in sys.path:
    sys.path.insert(0, _pkg_dir)

if "--mcp" in sys.argv:
    # TODO: MCP stdio 模式（未来实现）
    print("MCP stdio mode not yet implemented. Use HTTP mode instead.")
    sys.exit(1)
else:
    # HTTP API 模式 — 向后兼容
    from adapters.http_api import app, memory_agent
    import uvicorn

    if __name__ == "__main__":
        print("=" * 60)
        print("  EchoMind Memory v1.0.8 — HTTP API Mode")
        print("  Endpoint: http://localhost:8005")
        print("  Docs:     http://localhost:8005/docs")
        print("=" * 60)
        memory_agent.enable_persistence()
        uvicorn.run(app, host="0.0.0.0", port=8005, log_level="info")