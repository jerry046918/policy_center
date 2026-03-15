"""定时任务调度器（APScheduler）"""
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
import logging

logger = logging.getLogger(__name__)

# 全局调度器
scheduler = AsyncIOScheduler()


def start_scheduler():
    """启动调度器"""
    # 每日凌晨0:05执行政策过期
    @scheduler.scheduled_job(CronTrigger(hour=0, minute=5))
    async def expire_policies():
        logger.info("Running policy expiration job")
        from app.services.policy_service import PolicyService
        from app.database import async_session

        async with async_session() as session:
            service = PolicyService(session)
            expired_count = await service.expire_outdated()
            logger.info(f"Expired {expired_count} policies")

    # 每小时更新统计
    @scheduler.scheduled_job(CronTrigger(minute=0))
    async def update_statistics():
        logger.info("Running statistics update job")
        # TODO: 实现统计更新逻辑

    # 启动调度器
    scheduler.start()
    logger.info("Scheduler started")


def stop_scheduler():
    """停止调度器"""
    scheduler.shutdown()
    logger.info("Scheduler stopped")
