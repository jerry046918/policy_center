"""MCP 接口测试"""
import pytest
from httpx import AsyncClient
from app.main import app


@pytest.mark.asyncio
async def test_get_policy_schema():
    """测试获取政策 Schema"""
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get(
            "/mcp/tools/get_policy_schema",
            params={"policy_type": "social_insurance_base", "include_examples": "true"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "schema" in data
        assert "fields" in data["schema"]


@pytest.mark.asyncio
async def test_check_duplicate_no_match():
    """测试重复检查（无匹配）"""
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post(
            "/mcp/tools/check_duplicate",
            json={
                "region_code": "110000",
                "effective_start": "2099-01-01"
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert data["is_duplicate"] is False
