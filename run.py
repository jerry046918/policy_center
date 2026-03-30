#!/usr/bin/env python
"""启动脚本"""
import uvicorn
import os
import sys

# 确保项目根目录在路径中
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

if __name__ == "__main__":
    debug = os.environ.get("DEBUG", "false").lower() == "true"
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=debug,
        log_level="info"
    )
