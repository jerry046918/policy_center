"""数据库连接配置"""
from sqlalchemy import create_engine, Column, Text, Integer, select, func
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base
from app.config import settings
import logging
import json
import os
from datetime import datetime

logger = logging.getLogger(__name__)

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


async def _migrate_add_missing_columns():
    """
    为已存在的表补齐新增列。

    SQLAlchemy 的 create_all 只创建不存在的表，不会修改已有表结构。
    这里手动检测并 ALTER TABLE 添加缺失的列，实现简易迁移。
    """
    from sqlalchemy import text

    migrations = [
        # (table, column, type_sql)
        ("policies", "extension_data", "TEXT"),
        ("policy_type_definitions", "is_builtin", "INTEGER DEFAULT 0"),
        ("policy_type_definitions", "icon", "TEXT"),
        ("policy_type_definitions", "policy_count", "INTEGER DEFAULT 0"),
    ]

    async with engine.begin() as conn:
        for table, column, col_type in migrations:
            try:
                # 尝试查询该列，如果不存在会报错
                await conn.execute(text(f"SELECT {column} FROM {table} LIMIT 0"))
            except Exception:
                # 列不存在，添加它
                try:
                    await conn.execute(text(
                        f"ALTER TABLE {table} ADD COLUMN {column} {col_type}"
                    ))
                    logger.info(f"Migration: added column {table}.{column}")
                except Exception as e:
                    # 可能表本身也不存在（create_all 会创建），忽略
                    logger.debug(f"Migration skip {table}.{column}: {e}")


async def init_db():
    """初始化数据库（创建表）"""
    # 导入所有模型以确保它们被注册
    from app.models.region import Region
    from app.models.policy import Policy, PolicySocialInsurance, PolicyHousingFund
    from app.models.policy_type import PolicyTypeDefinition
    from app.models.policy_avg_salary import PolicyAvgSalary
    from app.models.policy_talent import PolicyTalent
    from app.models.review import ReviewQueue
    from app.models.version import PolicyVersion
    from app.models.audit import AuditLog
    from app.models.agent import AgentCredential, User

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # 补齐已有表缺失的新列（SQLite 的 create_all 不会 ALTER 已有表）
    await _migrate_add_missing_columns()

    # 注册内置政策类型
    from app.services.builtin_policy_types import register_builtin_types, sync_builtin_types_to_db, sync_db_policy_types
    register_builtin_types()
    logger.info("Built-in policy types registered")

    # 将内置类型同步到数据库（以便管理后台展示）
    async with async_session() as session:
        try:
            count = await sync_builtin_types_to_db(session)
            if count > 0:
                logger.info(f"Synced {count} built-in policy types to database")
        except Exception as e:
            logger.warning(f"Failed to sync built-in types to DB: {e}")

    # 从数据库加载动态类型
    async with async_session() as session:
        try:
            count = await sync_db_policy_types(session)
            if count > 0:
                logger.info(f"Loaded {count} dynamic policy types from database")
        except Exception as e:
            logger.warning(f"Failed to load dynamic types from DB: {e}")

    # 创建默认管理员用户
    async with async_session() as session:
        try:
            result = await session.execute(select(User).where(User.username == "admin"))
            if not result.scalar_one_or_none():
                from datetime import datetime
                from app.api.auth import hash_password
                import uuid

                admin = User(
                    user_id=str(uuid.uuid4()),
                    username="admin",
                    password_hash=hash_password("admin123"),
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

    # Migrate social_insurance_base -> social_insurance + housing_fund
    async with async_session() as session:
        try:
            from app.models.policy import PolicyHousingFund
            from sqlalchemy import text
            from datetime import datetime
            import uuid as uuid_mod

            # Step 1: Rename policy_type (use raw SQL to avoid model issues)
            rename_result = await session.execute(
                text("UPDATE policies SET policy_type = 'social_insurance' WHERE policy_type = 'social_insurance_base'")
            )
            renamed_count = rename_result.rowcount

            # Step 2: Split HF data - use raw SQL to read old columns that are no longer in the ORM model
            rows = await session.execute(
                text("""
                    SELECT si.policy_id, si.hf_upper_limit, si.hf_lower_limit,
                           si.is_retroactive, si.retroactive_start, si.retroactive_months, si.special_notes
                    FROM policy_social_insurance si
                    WHERE si.hf_upper_limit IS NOT NULL
                """)
            )
            si_with_hf = rows.fetchall()

            split_count = 0
            for row in si_with_hf:
                si_policy_id, hf_upper, hf_lower, is_retro, retro_start, retro_months, notes = row

                # Check if HF policy already exists for this source policy
                existing = await session.execute(
                    select(PolicyHousingFund).where(PolicyHousingFund.policy_id == si_policy_id)
                )
                if existing.scalar_one_or_none():
                    continue  # Already migrated (HF record attached to same policy_id)

                # Get the original policy
                orig = await session.execute(
                    select(Policy).where(Policy.policy_id == si_policy_id)
                )
                orig_policy = orig.scalar_one_or_none()
                if not orig_policy or not hf_upper:
                    continue

                hf_policy_id = str(uuid_mod.uuid4())
                now = datetime.utcnow().isoformat()

                title = orig_policy.title
                if "社保" in title or "社会保险" in title:
                    hf_title = title.replace("社保", "公积金").replace("社会保险", "公积金")
                else:
                    hf_title = f"{title}（公积金）"

                hf_policy = Policy(
                    policy_id=hf_policy_id,
                    policy_type="housing_fund",
                    title=hf_title,
                    region_code=orig_policy.region_code,
                    published_at=orig_policy.published_at,
                    effective_start=orig_policy.effective_start,
                    effective_end=orig_policy.effective_end,
                    policy_year=orig_policy.policy_year,
                    status=orig_policy.status,
                    version=1,
                    created_by="system_migration",
                    created_at=now,
                    updated_at=now,
                )
                session.add(hf_policy)

                hf_ext = PolicyHousingFund(
                    policy_id=hf_policy_id,
                    hf_upper_limit=hf_upper,
                    hf_lower_limit=hf_lower,
                    is_retroactive=is_retro,
                    retroactive_start=retro_start,
                    retroactive_months=retro_months,
                    special_notes=notes,
                )
                session.add(hf_ext)
                split_count += 1

            if renamed_count or split_count:
                await session.commit()
                logger.info(f"Migration: renamed {renamed_count} policies to social_insurance, created {split_count} housing_fund policies")
        except Exception as e:
            logger.warning(f"Migration check: {e}")


async def get_session() -> AsyncSession:
    """获取数据库会话（依赖注入）"""
    async with async_session() as session:
        try:
            yield session
        finally:
            await session.close()
