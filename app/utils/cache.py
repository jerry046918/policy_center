"""内存缓存（替代 Redis）"""
from cachetools import TTLCache
from typing import Optional, Any
import json

# 全局缓存实例
_cache = TTLCache(maxsize=1000, ttl=300)  # 最多1000条，5分钟过期


def get_cached(key: str) -> Optional[Any]:
    """获取缓存"""
    value = _cache.get(key)
    if value:
        try:
            return json.loads(value)
        except:
            return value
    return None


def set_cached(key: str, value: Any, ttl: int = 300) -> None:
    """设置缓存"""
    if isinstance(value, (dict, list)):
        value = json.dumps(value)
    _cache[key] = value


def delete_cached(key: str) -> bool:
    """删除缓存"""
    if key in _cache:
        del _cache[key]
        return True
    return False


def clear_cache() -> None:
    """清空缓存"""
    _cache.clear()


# 装饰器版本
def cached(key_prefix: str, ttl: int = 300):
    """缓存装饰器"""
    def decorator(func):
        async def wrapper(*args, **kwargs):
            # 生成缓存键
            key = f"{key_prefix}:{':'.join(str(a) for a in args)}"
            if kwargs:
                key += f":{':'.join(f'{k}={v}' for k, v in sorted(kwargs.items()))}"

            # 尝试获取缓存
            cached_value = get_cached(key)
            if cached_value is not None:
                return cached_value

            # 执行函数
            result = await func(*args, **kwargs)

            # 存储缓存
            set_cached(key, result, ttl)

            return result
        return wrapper
    return decorator
