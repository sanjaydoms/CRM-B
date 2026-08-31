import json
import logging
from typing import Any, Optional, Union

from django.conf import settings
from upstash_redis import Redis

logger = logging.getLogger(__name__)


def get_redis_client() -> Redis:
    """Returns an instance of Upstash Redis client initialized from Django settings."""
    raw_url = str(getattr(settings, 'UPSTASH_REDIS_REST_URL', 'https://charmed-mastiff-150004.upstash.io'))
    raw_token = str(getattr(settings, 'UPSTASH_REDIS_REST_TOKEN', 'gQAAAAAAAkn0AAIgcDFhMjY5MTkxMTQ5YzM0OTU2YTljZDMwNDQwNjNkYzc3Zg'))
    
    url = raw_url.strip().strip('\'"')
    token = raw_token.strip().strip('\'"')
    return Redis(url=url, token=token)



class RedisService:
    _client: Optional[Redis] = None

    @classmethod
    def reset_client(cls) -> None:
        cls._client = None

    @classmethod
    def get_client(cls) -> Redis:
        if cls._client is None:
            cls._client = get_redis_client()
        return cls._client


    @classmethod
    def ping(cls) -> bool:
        try:
            res = cls.get_client().ping()
            return res == "PONG" or res is True
        except Exception:
            logger.exception("Failed to ping Upstash Redis")
            return False

    @classmethod
    def set(cls, key: str, value: Union[str, dict, list], ex: Optional[int] = None) -> bool:
        try:
            if isinstance(value, (dict, list)):
                value_str = json.dumps(value)
            else:
                value_str = str(value)
            
            if ex:
                cls.get_client().set(key, value_str, ex=ex)
            else:
                cls.get_client().set(key, value_str)
            return True
        except Exception:
            logger.exception("Redis set error for key: %s", key)
            return False

    @classmethod
    def get(cls, key: str, parse_json: bool = False) -> Optional[Any]:
        try:
            val = cls.get_client().get(key)
            if val is None:
                return None
            if parse_json and isinstance(val, str):
                try:
                    return json.loads(val)
                except json.JSONDecodeError:
                    return val
            return val
        except Exception:
            logger.exception("Redis get error for key: %s", key)
            return None

    @classmethod
    def rpush(cls, key: str, value: Union[str, dict]) -> bool:
        try:
            if isinstance(value, (dict, list)):
                value_str = json.dumps(value)
            else:
                value_str = str(value)
            cls.get_client().rpush(key, value_str)
            return True
        except Exception:
            logger.exception("Redis rpush error for key: %s", key)
            return False

    @classmethod
    def lpop(cls, key: str, parse_json: bool = False) -> Optional[Any]:
        try:
            val = cls.get_client().lpop(key)
            if val is None:
                return None
            if parse_json and isinstance(val, str):
                try:
                    return json.loads(val)
                except json.JSONDecodeError:
                    return val
            return val
        except Exception:
            logger.exception("Redis lpop error for key: %s", key)
            return None

    @classmethod
    def delete(cls, key: str) -> bool:
        try:
            cls.get_client().delete(key)
            return True
        except Exception:
            logger.exception("Redis delete error for key: %s", key)
            return False
