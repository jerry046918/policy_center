"""FastAPI 主应用"""
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
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
    level=getattr(logging, settings.LOG_LEVEL),
    format='{"timestamp": "%(asctime)s", "level": "%(levelname)s", "message": "%(message)s"}'
)
logger = logging.getLogger(__name__)

_scheduler = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    global _scheduler

    # 启动时
    logger.info(f"Starting {settings.APP_NAME} v{settings.APP_VERSION}")

    # 初始化数据库
    await init_db()
    logger.info("Database initialized")

    # 创建上传目录
    os.makedirs(settings.STORAGE_PATH, exist_ok=True)
    os.makedirs("./data", exist_ok=True)

    # Demo 模式：写入样本数据 + 启动定时重置
    if settings.DEMO_MODE:
        from app.demo_seed import reset_demo_data
        logger.info("Demo mode enabled — seeding initial data")
        await reset_demo_data()
        logger.info("Demo seed complete")

        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        from apscheduler.triggers.cron import CronTrigger

        _scheduler = AsyncIOScheduler(timezone="Asia/Shanghai")

        # 解析 DEMO_RESET_CRON（格式: "分 时 日 月 星期"）
        parts = settings.DEMO_RESET_CRON.split()
        if len(parts) == 5:
            minute, hour, day, month, day_of_week = parts
        else:
            minute, hour, day, month, day_of_week = "0", "3", "*", "*", "*"

        async def _scheduled_reset():
            logger.info("Scheduled demo data reset starting")
            await reset_demo_data()
            logger.info("Scheduled demo data reset done")

        _scheduler.add_job(
            _scheduled_reset,
            CronTrigger(
                minute=minute, hour=hour,
                day=day, month=month, day_of_week=day_of_week,
                timezone="Asia/Shanghai",
            ),
            id="demo_reset",
            replace_existing=True,
        )
        _scheduler.start()
        logger.info(f"Demo reset scheduler started (cron: {settings.DEMO_RESET_CRON})")

    yield

    # 关闭时
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
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
# allow_origins=["*"] with allow_credentials=True is rejected by browsers; use explicit
# origins in production, or allow all only when credentials are not needed.
_cors_origins = os.environ.get("CORS_ORIGINS", "").strip()
_allow_origins = [o.strip() for o in _cors_origins.split(",") if o.strip()] if _cors_origins else ["*"]
_allow_credentials = bool(_cors_origins)  # only send credentials when origins are explicitly listed

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allow_origins,
    allow_credentials=_allow_credentials,
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


# 静态文件目录（生产模式：前端构建产物由 FastAPI 托管）
STATIC_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "web", "dist")


@app.get("/", tags=["根路径"], include_in_schema=False)
async def root():
    """根路径：生产模式返回前端页面，开发模式返回 API 信息"""
    index_html = os.path.join(STATIC_DIR, "index.html")
    if os.path.isfile(index_html):
        return FileResponse(index_html)
    return {
        "name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "docs": "/docs",
        "agent_api": "/api/agent"
    }


# 静态资源挂载
_assets_dir = os.path.join(STATIC_DIR, "assets")
if os.path.isdir(STATIC_DIR):
    # 静态资源（JS/CSS/images）— only mount if the assets sub-directory exists
    if os.path.isdir(_assets_dir):
        app.mount("/assets", StaticFiles(directory=_assets_dir), name="static-assets")

    # SPA fallback: 所有未匹配的路径返回 index.html
    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_spa(full_path: str):
        # Resolve the requested path and ensure it stays within STATIC_DIR (no path traversal)
        requested = os.path.realpath(os.path.join(STATIC_DIR, full_path))
        if requested.startswith(os.path.realpath(STATIC_DIR) + os.sep) and os.path.isfile(requested):
            return FileResponse(requested)
        return FileResponse(os.path.join(STATIC_DIR, "index.html"))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
