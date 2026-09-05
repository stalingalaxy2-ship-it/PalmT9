# -*- coding: utf-8 -*-
"""
config.py —— PalmT9 配置读写
=============================
持久化用户标定结果(阈值等), 启动时加载, 避免每次手动调参。
"""
import json
import os

DEFAULT_CONFIG = {
    "threshold": 0.34,
    "calibrated": False,
    "hand_scale": None,   # 标定时测得的手部尺度(参考值)
}

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")


def load_config(path=None):
    """读取配置; 不存在或损坏则返回默认并补写一份。"""
    if path is None:
        path = CONFIG_PATH
    cfg = dict(DEFAULT_CONFIG)
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                cfg.update(data)
    except Exception:
        pass
    return cfg


def save_config(cfg, path=None):
    """写配置(合并默认, 保证字段齐全)。"""
    if path is None:
        path = CONFIG_PATH
    merged = dict(DEFAULT_CONFIG)
    merged.update(cfg or {})
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(merged, f, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False
