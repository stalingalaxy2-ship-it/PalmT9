# -*- coding: utf-8 -*-
"""
retry_utils.py —— 429 限流重试工具
====================================
按用户要求：遇到 429 / TPM 限流，最多重试 10000 次。
做法不是无脑狂发，而是「指数退避 + 随机抖动 + 上限封顶」：
失败越多次等待越长（封顶 max_delay），既不死等也不打爆对方，
等效于「耐心地一直重试直到恢复」。

用法:
    from retry_utils import retry_on_429

    @retry_on_429()                     # 默认最多 10000 次
    def call_llm(...): ...

    @retry_on_429(max_attempts=10000, base_delay=1.0, max_delay=30.0)
    def call_api(...): ...
"""
import random
import time
from functools import wraps


def _is_retryable(exc: Exception) -> bool:
    """判断是否为限流/临时错误(429 / TPM / rate / 5xx)。"""
    msg = str(exc).lower()
    code = getattr(exc, "status_code", None) or getattr(exc, "code", None)
    if code in (429, 500, 502, 503, 504):
        return True
    return ("429" in msg or "tpm" in msg or "rate limit" in msg
            or "ratelimit" in msg or "too many" in msg
            or "exhausted" in msg or "temporarily" in msg)


def retry_on_429(max_attempts=10000, base_delay=1.0, max_delay=30.0):
    """对限流错误做指数退避+抖动重试; 非限流错误直接抛出。

    max_attempts=10000: 不是固定间隔狂发一万次, 而是退避到 max_delay 后
    以该间隔持续重试——实质是"长时间不放弃", 但不会加剧限流。
    """
    def deco(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            delay = base_delay
            last_exc = None
            for attempt in range(1, max_attempts + 1):
                try:
                    return fn(*args, **kwargs)
                except Exception as e:  # noqa: BLE001
                    last_exc = e
                    if not _is_retryable(e) or attempt == max_attempts:
                        raise
                    sleep_s = min(delay, max_delay) * (0.5 + random.random())
                    time.sleep(sleep_s)
                    delay = min(delay * 2, max_delay)
            raise last_exc
        return wrapper
    return deco


def call_with_retry(fn, *args, max_attempts=10000, base_delay=1.0,
                    max_delay=30.0, **kwargs):
    """函数式用法(不用装饰器)。"""
    wrapped = retry_on_429(max_attempts, base_delay, max_delay)(fn)
    return wrapped(*args, **kwargs)
