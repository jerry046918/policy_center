"""测试配置"""
import pytest
import asyncio

# 配置 asyncio 事件循环
@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()
