"""数据库连接配置"""
from sqlalchemy import create_engine, Column, Text, Integer, select, func
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base
from app.config import settings
from passlib.context import CryptContext
import logging
import json
import os

logger = logging.getLogger(__name__)

# 密码哈希工具
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# 创建异步引擎
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
)

# 创建异步会话工厂
async_session = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

# 声明基类
Base = declarative_base()


def _build_regions_from_json(data: dict) -> list:
    """从 JSON 数据构建地区列表"""
    regions = []

    # 添加国家节点
    regions.append({
        "code": "000000",
        "name": "中国",
        "level": "country",
        "parent_code": None,
        "full_path": "中国",
        "path_materialized": "000000"
    })

    # 添加省份和城市
    for province in data.get("provinces", []):
        province_code = province["code"]
        province_name = province["name"]

        # 添加省份
        regions.append({
            "code": province_code,
            "name": province_name,
            "level": "province",
            "parent_code": "000000",
            "full_path": f"中国/{province_name}",
            "path_materialized": f"000000.{province_code}"
        })

        # 添加该省份下的城市
        cities = data.get("cities", {}).get(province_code, [])
        for city in cities:
            city_code = city["code"]
            city_name = city["name"]
            regions.append({
                "code": city_code,
                "name": city_name,
                "level": "city",
                "parent_code": province_code,
                "full_path": f"中国/{province_name}/{city_name}",
                "path_materialized": f"000000.{province_code}.{city_code}"
            })

    return regions


async def init_db():
    """初始化数据库（创建表）"""
    # 导入所有模型以确保它们被注册
    from app.models.region import Region
    from app.models.policy import Policy, PolicySocialInsurance
    from app.models.review import ReviewQueue
    from app.models.version import PolicyVersion
    from app.models.audit import AuditLog
    from app.models.agent import AgentCredential, User

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # 创建默认管理员用户
    async with async_session() as session:
        try:
            result = await session.execute(select(User).where(User.username == "admin"))
            if not result.scalar_one_or_none():
                from datetime import datetime
                import uuid

                admin = User(
                    user_id=str(uuid.uuid4()),
                    username="admin",
                    password_hash=pwd_context.hash("admin123"),
                    email="admin@example.com",
                    display_name="管理员",
                    role="admin",
                    is_active=1,
                    created_at=datetime.utcnow().isoformat()
                )
                session.add(admin)
                await session.commit()
                logger.info("Default admin user created with hashed password")
        except Exception as e:
            logger.warning(f"Failed to create default admin: {e}")

    # 自动初始化地区数据
    async with async_session() as session:
        try:
            # 检查是否已有地区数据
            result = await session.execute(select(func.count()).select_from(Region))
            count = result.scalar()

            if count == 0:
                # 从 JSON 文件加载地区数据
                data_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "regions.json")

                if os.path.exists(data_file):
                    with open(data_file, "r", encoding="utf-8") as f:
                        data = json.load(f)

                    regions_data = _build_regions_from_json(data)

                    # 批量插入
                    for region_data in regions_data:
                        region = Region(**region_data)
                        session.add(region)

                    await session.commit()
                    logger.info(f"Auto-initialized {len(regions_data)} regions from {data_file}")
                else:
                    logger.warning(f"Regions data file not found: {data_file}")
        except Exception as e:
            logger.warning(f"Failed to auto-initialize regions: {e}")


async def get_session() -> AsyncSession:
    """获取数据库会话（依赖注入）"""
    async with async_session() as session:
        try:
            yield session
        finally:
            await session.close()
