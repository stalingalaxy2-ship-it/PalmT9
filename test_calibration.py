# -*- coding: utf-8 -*-
"""校正→配置→使用 闭环测试"""
import os

import config as config_mod
import gesture_core as gc


def _tmp_path(tmp_path, monkeypatch):
    p = tmp_path / "config.json"
    monkeypatch.setattr(config_mod, "CONFIG_PATH", str(p))
    return str(p)


def test_calibration_roundtrip(tmp_path, monkeypatch):
    """标定算阈值 -> 写 config -> 再加载 -> palm_t9 用该阈值。"""
    path = _tmp_path(tmp_path, monkeypatch)
    # 模拟标定: 用户敲键测得的最小距离比
    min_ratios = [0.10, 0.12, 0.30, 0.42]
    thr = gc.recommend_threshold(min_ratios)
    assert 0.2 <= thr <= 0.7

    # 写 config
    assert config_mod.save_config({"threshold": round(thr, 3), "calibrated": True})
    # 读回
    cfg = config_mod.load_config()
    assert cfg["calibrated"] is True
    assert abs(cfg["threshold"] - thr) < 1e-2


def test_default_when_uncalibrated(tmp_path, monkeypatch):
    path = _tmp_path(tmp_path, monkeypatch)
    cfg = config_mod.load_config()
    assert cfg["calibrated"] is False
    assert cfg["threshold"] == 0.34


def test_recommend_threshold_uses_max():
    """阈值由最难够到的键(最大 min_ratio)决定。"""
    t = gc.recommend_threshold([0.05, 0.08, 0.50], safety=1.2)
    assert abs(t - 0.60) < 1e-6
