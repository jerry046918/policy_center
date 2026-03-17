"""FastAPI 主应用"""
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import time
import uuid
import logging
import os

from sqlalchemy import text

from app.config import settings
from app.database import init_db, engine
# Agent REST API (replaces MCP)
from app.api.agent import router as agent_router

# 配置日志
logging.basicConfig(
    level=getattr(logging, settings.MCP_LOG_LEVEL),
    format='{"timestamp": "%(asctime)s", "level": "%(levelname)s", "message": "%(message)s"}'
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时
    logger.info(f"Starting {settings.APP_NAME} v{settings.APP_VERSION}")

    # 初始化数据库
    await init_db()
    logger.info("Database initialized")

    # 创建上传目录
    os.makedirs(settings.STORAGE_PATH, exist_ok=True)
    os.makedirs("./data", exist_ok=True)

    yield

    # 关闭时
    logger.info("Shutting down...")
    await engine.dispose()


# 创建应用
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="政策数据管理平台 - REST API 数据基础设施",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# 请求中间件
@app.middleware("http")
async def add_request_context(request: Request, call_next):
    request_id = str(uuid.uuid4())[:8]
    request.state.request_id = request_id
    request.state.start_time = time.time()

    response = await call_next(request)

    response.headers["X-Request-ID"] = request_id
    elapsed = (time.time() - request.state.start_time) * 1000
    response.headers["X-Response-Time"] = f"{elapsed:.2f}ms"

    return response


# 全局异常处理
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "error": {
                "code": "INTERNAL_ERROR",
                "message": str(exc) if settings.DEBUG else "An unexpected error occurred"
            },
            "request_id": getattr(request.state, "request_id", None)
        }
    )


# 注册路由
from app.api.auth import router as auth_router
from app.api.policies import router as policies_router
from app.api.reviews import router as reviews_router
from app.api.admin import router as admin_router
from app.api.dashboard import router as dashboard_router

app.include_router(auth_router, prefix="/api/v1/auth", tags=["认证"])
app.include_router(policies_router, prefix="/api/v1/policies", tags=["政策管理"])
app.include_router(reviews_router, prefix="/api/v1/reviews", tags=["审核中心"])
app.include_router(admin_router, prefix="/api/v1/admin", tags=["系统管理"])
app.include_router(dashboard_router, prefix="/api/v1/dashboard", tags=["数据看板"])

# Agent REST API (replaces MCP)
app.include_router(agent_router, prefix="/api/agent", tags=["Agent API"])


# 健康检查
@app.get("/health", tags=["健康检查"])
async def health():
    """存活检查"""
    return {
        "status": "healthy",
        "version": settings.APP_VERSION,
        "timestamp": time.time()
    }


@app.get("/ready", tags=["健康检查"])
async def ready():
    """就绪检查"""
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return {"status": "ready", "database": "connected"}
    except Exception as e:
        return JSONResponse(
            status_code=503,
            content={"status": "not_ready", "error": str(e)}
        )


@app.get("/", tags=["根路径"])
async def root():
    """API 根路径"""
    return {
        "name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "docs": "/docs",
        "agent_api": "/api/agent"
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
