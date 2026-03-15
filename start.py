#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
一键启动脚本 - 同时启动前后端服务
"""
import subprocess
import sys
import os
import time
import webbrowser
import threading
import sqlite3
import hashlib
import json
from datetime import datetime

# 修复 Windows 控制台编码
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')


def check_dependencies():
    """检查依赖是否安装"""
    print("Checking dependencies...")

    # 检查 Python 依赖
    try:
        import fastapi
        import uvicorn
        print("[OK] Backend dependencies installed")
    except ImportError:
        print("Installing backend dependencies...")
        subprocess.run([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"], check=True)

    # 检查前端依赖
    web_dir = os.path.join(os.path.dirname(__file__), "web")
    node_modules = os.path.join(web_dir, "node_modules")
    if os.path.exists(web_dir):
        if not os.path.exists(node_modules):
            print("Installing frontend dependencies...")
            subprocess.run(["npm", "install"], cwd=web_dir, shell=True, check=True)
        else:
            print("[OK] Frontend dependencies installed")


def create_test_agent():
    """创建测试 Agent 凭据"""
    api_key = 'pk_test_1234567890abcdef1234567890abcdef'
    api_key_hash = hashlib.sha256(api_key.encode()).hexdigest()
    db_path = './data/policy_center.db'

    # 确保数据目录存在
    os.makedirs('./data', exist_ok=True)

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # 检查表是否存在，不存在则创建
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS agent_credentials (
            agent_id TEXT PRIMARY KEY,
            agent_name TEXT NOT NULL,
            api_key_hash TEXT NOT NULL,
            api_key_prefix TEXT NOT NULL,
            description TEXT,
            permissions TEXT,
            rate_limit INTEGER DEFAULT 60,
            is_active INTEGER DEFAULT 1,
            last_used_at TEXT,
            created_at TEXT,
            expires_at TEXT,
            created_by TEXT
        )
    ''')
    conn.commit()

    try:
        cursor.execute('''
            INSERT INTO agent_credentials
            (agent_id, agent_name, api_key_hash, api_key_prefix, description, permissions, rate_limit, is_active, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', ('test_agent_001', 'Test Agent', api_key_hash, 'pk_test_123', 'Test agent for development',
              json.dumps(['submit', 'query']), 1000, 1, datetime.now().isoformat()))
        conn.commit()
        print("[OK] Test agent created")
    except sqlite3.IntegrityError:
        print("[OK] Test agent already exists")
    finally:
        conn.close()

    return api_key


def start_backend():
    """启动后端服务"""
    print("Starting backend server (port 8000)...")
    return subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--reload", "--port", "8000"],
        cwd=os.path.dirname(__file__)
    )


def start_frontend():
    """启动前端服务"""
    print("Starting frontend server (port 3000)...")
    web_dir = os.path.join(os.path.dirname(__file__), "web")
    return subprocess.Popen(
        ["npm", "run", "dev"],
        cwd=web_dir,
        shell=True
    )


def open_browser():
    """延迟打开浏览器"""
    time.sleep(3)
    print("\n" + "="*60)
    print("  Services Started!")
    print("="*60)
    print("  Frontend:  http://localhost:3000")
    print("  API Docs:  http://localhost:8000/docs")
    print("  Health:    http://localhost:8000/health")
    print("="*60)
    print("  Test API Key: pk_test_1234567890abcdef1234567890abcdef")
    print("="*60 + "\n")
    webbrowser.open("http://localhost:3000")


def main():
    print("\n" + "="*60)
    print("  Policy Center - Quick Start")
    print("="*60 + "\n")

    # 检查并安装依赖
    check_dependencies()
    print()

    # 创建测试 Agent
    api_key = create_test_agent()
    print()

    # 启动服务
    backend = start_backend()
    frontend = None

    # 检查前端是否存在
    web_dir = os.path.join(os.path.dirname(__file__), "web")
    if os.path.exists(web_dir):
        frontend = start_frontend()

    # 打开浏览器
    threading.Thread(target=open_browser, daemon=True).start()

    print("\nPress Ctrl+C to stop all services...\n")

    try:
        # 等待进程
        backend.wait()
        if frontend:
            frontend.wait()
    except KeyboardInterrupt:
        print("\nStopping services...")
        backend.terminate()
        if frontend:
            frontend.terminate()
        print("Services stopped")


if __name__ == "__main__":
    main()
