"""Demo 模式数据重置模块

负责：
1. 完整重置所有业务数据，包括 users 和 agent_credentials
2. 重建默认管理员账号（admin / admin123）
3. 重建固定 Demo Agent API Key（明文由环境变量 DEMO_AGENT_API_KEY 提供）
4. 写入覆盖多种政策类型和多个城市的样本数据
5. 供 lifespan 启动时调用，以及 APScheduler 定时调用
"""
import uuid
import json
import hashlib
import logging
from datetime import datetime, timedelta

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session
from app.config import settings

logger = logging.getLogger(__name__)

# Demo Agent 固定 API Key 前缀，用于在管理后台展示
DEMO_AGENT_ID = "agent_demo0000000000"
DEMO_AGENT_NAME = "Demo Test Agent"

# ---------------------------------------------------------------------------
# 样本数据定义
# ---------------------------------------------------------------------------

# (region_code, city_name, si_upper, si_lower, hf_upper, hf_lower,
#  avg_salary_annual, si_effective, hf_effective, published)
_CITY_DATA = [
    ("110000", "北京",  35283,  6821, 35283,  2320, 185026, "2024-07-01", "2024-07-01", "2024-06-20"),
    ("310000", "上海",  34188,  7310, 34188,  2590, 191040, "2024-04-01", "2024-04-01", "2024-03-25"),
    ("440100", "广州",  26541,  2300, 26541,  1900, 139968, "2024-07-01", "2024-07-01", "2024-06-28"),
    ("440300", "深圳",  31884,  2360, 31884,  2100, 168012, "2024-07-01", "2024-07-01", "2024-06-25"),
    ("330100", "杭州",  26895,  2490, 26895,  2100, 142008, "2024-10-01", "2024-10-01", "2024-09-20"),
    ("320100", "南京",  22834,  2260, 22834,  1760, 120420, "2024-07-01", "2024-07-01", "2024-06-30"),
    ("510100", "成都",  18874,  2100, 18874,  1590, 100416, "2024-07-01", "2024-07-01", "2024-06-26"),
    ("420100", "武汉",  20204,  2220, 20204,  1720, 107040, "2024-07-01", "2024-07-01", "2024-06-28"),
    ("610100", "西安",  16872,  2100, 16872,  1500,  89508, "2024-07-01", "2024-07-01", "2024-06-25"),
    ("500000", "重庆",  16135,  2100, 16135,  1590,  85632, "2024-07-01", "2024-07-01", "2024-06-20"),
    ("350200", "厦门",  22640,  2432, 22640,  1856, 121032, "2024-10-01", "2024-10-01", "2024-09-28"),
    ("210100", "沈阳",  14804,  1975, 14804,  1480,  78732, "2024-07-01", "2024-07-01", "2024-06-30"),
]

_TALENT_POLICIES = [
    {
        "region_code": "110000",
        "city": "北京",
        "title": "北京市高层次人才引进与支持实施办法（2024年修订）",
        "published_at": "2024-03-15",
        "effective_start": "2024-04-01",
        "talent_categories": ["A类（国际顶尖人才）", "B类（国家级领军人才）", "C类（北京市高层次人才）"],
        "subsidy_standards": {
            "A类住房补贴": "最高300万元",
            "B类住房补贴": "最高200万元",
            "C类住房补贴": "最高100万元",
            "生活补贴": "A类每月1万元，B类每月5000元",
        },
        "education_requirement": "博士及以上或具有正高级职称",
        "age_limit": 55,
    },
    {
        "region_code": "440300",
        "city": "深圳",
        "title": "深圳市海外高层次人才认定和工作规程（2024版）",
        "published_at": "2024-05-10",
        "effective_start": "2024-06-01",
        "talent_categories": ["孔雀A类（杰出人才）", "孔雀B类（领军人才）", "孔雀C类（高层次人才）"],
        "subsidy_standards": {
            "A类安家费": "300万元",
            "B类安家费": "200万元",
            "C类安家费": "160万元",
            "租房补贴": "每月最高3000元，连续3年",
        },
        "education_requirement": "博士学位或正高职称",
        "age_limit": 50,
    },
    {
        "region_code": "330100",
        "city": "杭州",
        "title": "杭州市高层次人才分类认定办法（2024年）",
        "published_at": "2024-02-28",
        "effective_start": "2024-03-01",
        "talent_categories": ["A类", "B类", "C类", "D类", "E类"],
        "subsidy_standards": {
            "A类安家费": "300万元",
            "B类安家费": "150万元",
            "C类安家费": "100万元",
            "D类生活补贴": "每月2000元",
        },
        "education_requirement": "本科及以上（D、E类）；博士或副高以上（A-C类）",
        "age_limit": 50,
    },
]

_PENDING_REVIEWS = [
    {
        "region_code": "120000",
        "city": "天津",
        "policy_type": "social_insurance",
        "title": "天津市2024年度社会保险缴费工资基数上下限调整通知",
        "si_upper": 24819,
        "si_lower": 3974,
        "effective_start": "2024-07-01",
        "published_at": "2024-06-28",
        "priority": "high",
    },
    {
        "region_code": "320500",
        "city": "苏州",
        "policy_type": "housing_fund",
        "title": "苏州市2024年住房公积金缴存基数调整公告",
        "hf_upper": 26208,
        "hf_lower": 2280,
        "effective_start": "2024-07-01",
        "published_at": "2024-06-20",
        "priority": "normal",
    },
    {
        "region_code": "370100",
        "city": "济南",
        "policy_type": "social_insurance",
        "title": "济南市关于2024年度社会保险缴费基数核定工作的通知",
        "si_upper": 19827,
        "si_lower": 2340,
        "effective_start": "2024-07-01",
        "published_at": "2024-06-25",
        "priority": "normal",
    },
]


# ---------------------------------------------------------------------------
# 核心重置函数
# ---------------------------------------------------------------------------

async def reset_demo_data() -> None:
    """完整重置数据库并写入样本数据（幂等，可多次调用）。"""
    async with async_session() as session:
        try:
            await _clear_all_data(session)
            await _seed_admin_user(session)
            await _seed_demo_agent(session)
            await _seed_policies(session)
            await _seed_pending_reviews(session)
            await session.commit()
            logger.info("Demo data reset complete")
        except Exception:
            await session.rollback()
            logger.exception("Demo data reset failed")
            raise


async def _clear_all_data(session: AsyncSession) -> None:
    """删除所有可重置的数据，保留 regions 和 policy_type_definitions。"""
    for table in [
        "policy_social_insurance",
        "policy_housing_fund",
        "policy_avg_salary",
        "policy_talent",
        "policy_versions",
        "audit_logs",
        "review_queue",
        "policies",
        "agent_credentials",
        "users",
    ]:
        await session.execute(text(f"DELETE FROM {table}"))
    logger.debug("Cleared all resettable tables")


async def _seed_admin_user(session: AsyncSession) -> None:
    """重建默认管理员账号。"""
    from app.api.auth import hash_password
    now = datetime.utcnow().isoformat()
    await session.execute(text("""
        INSERT INTO users
          (user_id, username, password_hash, email, display_name,
           role, is_active, created_at)
        VALUES
          (:uid, 'admin', :pw_hash, 'admin@demo.local', '管理员',
           'admin', 1, :now)
    """), {
        "uid": str(uuid.uuid4()),
        "pw_hash": hash_password("admin123"),
        "now": now,
    })
    logger.debug("Admin user seeded")


async def _seed_demo_agent(session: AsyncSession) -> None:
    """重建固定 Demo Agent API Key。

    明文 key 由环境变量 DEMO_AGENT_API_KEY 提供；
    若未设置则使用内置默认值（仅适合非公开测试）。
    """
    api_key = settings.DEMO_AGENT_API_KEY
    api_key_hash = hashlib.sha256(api_key.encode()).hexdigest()
    api_key_prefix = api_key[:12]
    now = datetime.utcnow().isoformat()

    await session.execute(text("""
        INSERT INTO agent_credentials
          (agent_id, agent_name, api_key_hash, api_key_prefix,
           description, permissions, rate_limit, is_active, created_at)
        VALUES
          (:aid, :name, :hash, :prefix,
           :desc, '["submit","read"]', 120, 1, :now)
    """), {
        "aid": DEMO_AGENT_ID,
        "name": DEMO_AGENT_NAME,
        "hash": api_key_hash,
        "prefix": api_key_prefix,
        "desc": "Demo 测试用固定 API Key，每次重置后保持不变",
        "now": now,
    })
    logger.debug(f"Demo agent seeded (prefix: {api_key_prefix})")


async def _seed_policies(session: AsyncSession) -> None:
    """写入社保、公积金、社平工资的样本政策（status=active）。"""
    now = datetime.utcnow().isoformat()

    for (region_code, city, si_upper, si_lower, hf_upper, hf_lower,
         avg_annual, si_eff, hf_eff, published) in _CITY_DATA:

        year = int(si_eff[:4])

        # ── 社保基数 ────────────────────────────────────────────
        si_id = str(uuid.uuid4())
        await session.execute(text("""
            INSERT INTO policies
              (policy_id, policy_type, title, region_code,
               published_at, effective_start, policy_year,
               status, version, created_by, created_at, updated_at)
            VALUES
              (:pid, 'social_insurance', :title, :rc,
               :pub, :eff, :yr,
               'active', 1, 'demo_seed', :now, :now)
        """), {
            "pid": si_id,
            "title": f"关于{year}年度{city}市社会保险缴费工资基数上下限的通知",
            "rc": region_code,
            "pub": published,
            "eff": si_eff,
            "yr": year,
            "now": now,
        })
        await session.execute(text("""
            INSERT INTO policy_social_insurance
              (policy_id, si_upper_limit, si_lower_limit, is_retroactive, coverage_types)
            VALUES
              (:pid, :upper, :lower, 0,
               '["养老","医疗","失业","工伤","生育"]')
        """), {"pid": si_id, "upper": si_upper, "lower": si_lower})

        # ── 公积金基数 ───────────────────────────────────────────
        hf_id = str(uuid.uuid4())
        await session.execute(text("""
            INSERT INTO policies
              (policy_id, policy_type, title, region_code,
               published_at, effective_start, policy_year,
               status, version, created_by, created_at, updated_at)
            VALUES
              (:pid, 'housing_fund', :title, :rc,
               :pub, :eff, :yr,
               'active', 1, 'demo_seed', :now, :now)
        """), {
            "pid": hf_id,
            "title": f"{city}市{year}年住房公积金缴存基数上下限调整公告",
            "rc": region_code,
            "pub": published,
            "eff": hf_eff,
            "yr": year,
            "now": now,
        })
        await session.execute(text("""
            INSERT INTO policy_housing_fund
              (policy_id, hf_upper_limit, hf_lower_limit, is_retroactive)
            VALUES
              (:pid, :upper, :lower, 0)
        """), {"pid": hf_id, "upper": hf_upper, "lower": hf_lower})

        # ── 社会平均工资 ─────────────────────────────────────────
        avg_id = str(uuid.uuid4())
        avg_monthly = avg_annual // 12
        stats_year = year - 1  # 社平工资通常发布上一年数据
        await session.execute(text("""
            INSERT INTO policies
              (policy_id, policy_type, title, region_code,
               published_at, effective_start, policy_year,
               status, version, created_by, created_at, updated_at)
            VALUES
              (:pid, 'avg_salary', :title, :rc,
               :pub, :eff, :yr,
               'active', 1, 'demo_seed', :now, :now)
        """), {
            "pid": avg_id,
            "title": f"{city}市{stats_year}年度社会平均工资公告",
            "rc": region_code,
            "pub": published,
            "eff": si_eff,
            "yr": stats_year,
            "now": now,
        })
        await session.execute(text("""
            INSERT INTO policy_avg_salary
              (policy_id, avg_salary_total, avg_salary_monthly, statistics_year)
            VALUES
              (:pid, :total, :monthly, :yr)
        """), {"pid": avg_id, "total": avg_annual, "monthly": avg_monthly, "yr": stats_year})

    # ── 人才政策 ─────────────────────────────────────────────────
    for tp in _TALENT_POLICIES:
        t_id = str(uuid.uuid4())
        await session.execute(text("""
            INSERT INTO policies
              (policy_id, policy_type, title, region_code,
               published_at, effective_start, policy_year,
               status, version, created_by, created_at, updated_at)
            VALUES
              (:pid, 'talent_policy', :title, :rc,
               :pub, :eff, :yr,
               'active', 1, 'demo_seed', :now, :now)
        """), {
            "pid": t_id,
            "title": tp["title"],
            "rc": tp["region_code"],
            "pub": tp["published_at"],
            "eff": tp["effective_start"],
            "yr": int(tp["effective_start"][:4]),
            "now": now,
        })
        await session.execute(text("""
            INSERT INTO policy_talent
              (policy_id, talent_categories, subsidy_standards,
               education_requirement, age_limit,
               required_documents, certification_requirements)
            VALUES
              (:pid, :cats, :subs, :edu, :age, :docs, :certs)
        """), {
            "pid": t_id,
            "cats": json.dumps(tp["talent_categories"], ensure_ascii=False),
            "subs": json.dumps(tp["subsidy_standards"], ensure_ascii=False),
            "edu": tp["education_requirement"],
            "age": tp["age_limit"],
            "docs": json.dumps(["身份证明", "学历证书", "职称证书", "工作合同"], ensure_ascii=False),
            "certs": json.dumps({}, ensure_ascii=False),
        })

    logger.debug(f"Seeded {len(_CITY_DATA) * 3 + len(_TALENT_POLICIES)} policies")


async def _seed_pending_reviews(session: AsyncSession) -> None:
    """写入几条待审核记录，让审核中心页面有内容展示。"""
    now_dt = datetime.utcnow()
    now = now_dt.isoformat()

    priority_hours = {"urgent": 1, "high": 4, "normal": 24, "low": 72}

    for item in _PENDING_REVIEWS:
        r_id = str(uuid.uuid4())
        p_id = str(uuid.uuid4())
        hours = priority_hours.get(item["priority"], 24)
        sla = (now_dt + timedelta(hours=hours)).isoformat()

        if item["policy_type"] == "social_insurance":
            type_data = {
                "si_upper_limit": item["si_upper"],
                "si_lower_limit": item["si_lower"],
                "is_retroactive": False,
                "coverage_types": ["养老", "医疗", "失业", "工伤", "生育"],
            }
        else:
            type_data = {
                "hf_upper_limit": item["hf_upper"],
                "hf_lower_limit": item["hf_lower"],
                "is_retroactive": False,
            }

        submitted_data = {
            "title": item["title"],
            "region_code": item["region_code"],
            "policy_type": item["policy_type"],
            "published_at": item["published_at"],
            "effective_start": item["effective_start"],
            **type_data,
        }
        raw_evidence = json.dumps({
            "sources": [{
                "url": f"https://example.gov.cn/demo/{item['region_code']}",
                "title": item["title"],
                "extracted_text": f"（Demo 样本数据，仅供展示）{item['title']}",
            }]
        }, ensure_ascii=False)

        await session.execute(text("""
            INSERT INTO review_queue
              (review_id, policy_id, submitted_data, raw_evidence,
               status, priority, submit_type,
               submitted_by, submitted_at, sla_deadline,
               risk_level, risk_tags)
            VALUES
              (:rid, :pid, :data, :evidence,
               'pending', :priority, 'new',
               'demo_agent', :now, :sla,
               'low', '[]')
        """), {
            "rid": r_id,
            "pid": p_id,
            "data": json.dumps(submitted_data, ensure_ascii=False),
            "evidence": raw_evidence,
            "priority": item["priority"],
            "now": now,
            "sla": sla,
        })

    logger.debug(f"Seeded {len(_PENDING_REVIEWS)} pending reviews")
