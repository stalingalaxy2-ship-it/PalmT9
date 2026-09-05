# -*- coding: utf-8 -*-
"""PalmT9 单元测试套件（pytest）

运行: python -m pytest test_gesture_core.py -v
覆盖: 词典解码 / 候选提交与切换 / 退格 / 标定 / 触发状态机。
"""
import math

import pytest

import gesture_core as gc


# ---------------- 词典 ----------------
def test_word_to_seq():
    assert gc.word_to_seq("hello") == "43556"
    assert gc.word_to_seq("home") == "4663"
    assert gc.word_to_seq("world") == "96753"


def test_candidates_sorted_by_freq():
    c = gc.candidates_for(list("4663"))
    # 4663 = home / good / gone ... 最高频在前
    assert c[0][0] in ("home", "good")
    assert c[0][1] >= c[-1][1]


# ---------------- 状态机 ----------------
def test_commit_top1():
    s = gc.GestureState()
    s.digits = list("43556")  # hello
    w = gc.commit(s)
    assert w == "hello"
    assert s.committed == "hello "
    assert s.digits == []


def test_cycle_and_commit_second():
    s = gc.GestureState()
    s.digits = list("4663")  # home / good / ...
    c = gc.candidates_for(s.digits)
    assert len(c) >= 2
    second = c[1][0]
    gc.cycle_candidate(s)
    w = gc.commit(s)
    assert w == second


def test_cycle_wraps_around():
    s = gc.GestureState()
    s.digits = list("4663")
    n = len(gc.candidates_for(s.digits))
    for _ in range(n + 1):
        gc.cycle_candidate(s)
    assert s.sel_idx == (n + 1) % max(1, n)


def test_backspace_digit_then_char():
    s = gc.GestureState()
    s.digits = list("466")
    gc.backspace(s)
    assert s.digits == list("46")
    s.digits = []
    s.committed = "hello "
    gc.backspace(s)
    assert s.committed == "hello"


def test_commit_no_candidate_fallback():
    s = gc.GestureState()
    s.digits = list("999999")  # 词典里几乎不会有
    w = gc.commit(s)
    assert w == "999999"
    assert s.committed == "999999 "


def test_shift_capitalizes_next_word():
    s = gc.GestureState()
    s.digits = list("43556")  # hello
    s.shift = True
    w = gc.commit(s)
    assert w == "Hello"
    assert s.shift is False  # 一次性


def test_cycle_does_not_change_without_candidates():
    s = gc.GestureState()
    s.digits = list("999999")
    gc.cycle_candidate(s)
    assert s.sel_idx == 0


# ---------------- 标定 ----------------
def test_estimate_hand_scale():
    lm = [(0.5, 0.85)] + [(0.5, 0.5)] * 3 + [(0.5, 0.5)] * 5 + [(0.5, 0.5)] * 4 + [(0.5, 0.5)] * 5 + [(0.5, 0.5)] * 4
    # lm[0]=(0.5,0.85), lm[9]=(0.5,0.5) => scale=0.35
    assert abs(gc.estimate_hand_scale(lm) - 0.35) < 1e-6


def test_recommend_threshold_clamp_and_safety():
    assert gc.recommend_threshold([]) == 0.34
    # max=0.4, safety 1.4 => 0.56
    assert abs(gc.recommend_threshold([0.1, 0.3, 0.4], safety=1.4) - 0.56) < 1e-6
    # 夹到下限
    assert gc.recommend_threshold([0.05], safety=1.4, lo=0.2) == 0.2
    # 夹到上限
    assert gc.recommend_threshold([0.9], safety=1.4, hi=0.7) == 0.7


# ---------------- 中文拼音 ----------------
def test_pinyin_to_seq():
    assert gc.pinyin_to_seq("nihao") == "64426"
    assert gc.pinyin_to_seq("shijie") == "744543"


def test_candidates_cn():
    c = gc.candidates_cn(list("64426"))  # nihao
    assert c and c[0][0] == "你好"
    c2 = gc.candidates_cn(list("744543"))  # shijie
    assert c2 and c2[0][0] == "世界"


# ---------------- 触发状态机 ----------------
def _hand(role="L"):
    return gc.base_hand(role) if hasattr(gc, "base_hand") else None


def test_letter_trigger_updates_digits():
    s = gc.GestureState()
    # 直接构造: 让食指近端键(7)成为最近键且拇指快速接近
    lm = [(0.5, 0.85)] + [(0.45, 0.78), (0.40, 0.72), (0.37, 0.68), (0.38, 0.48)] \
        + [(0.40, 0.60), (0.38, 0.48), (0.37, 0.40), (0.36, 0.32)] \
        + [(0.50, 0.58), (0.50, 0.46), (0.50, 0.38), (0.50, 0.30)] \
        + [(0.60, 0.60), (0.62, 0.48), (0.63, 0.40), (0.64, 0.32)] \
        + [(0.68, 0.62), (0.71, 0.52), (0.72, 0.46), (0.73, 0.40)]
    # 拇指尖(4) 贴到食指近端(6) 附近
    lm[4] = lm[6]
    ev = gc.evaluate_frame({"L": lm}, s, 0.0)
    # 第一帧驻留计数=1, 不触发
    assert ev == []
    ev = gc.evaluate_frame({"L": lm}, s, 1 / 30)
    # 第二帧驻留=2, 但速度不够(拇指没动) => 仍不触发
    assert ev == []


def test_rest_hand_no_false_trigger():
    s = gc.GestureState()
    lm = [(0.5, 0.85)] + [(0.42, 0.78), (0.36, 0.72), (0.32, 0.68), (0.30, 0.66)] \
        + [(0.40, 0.60), (0.38, 0.48), (0.37, 0.40), (0.36, 0.32)] \
        + [(0.50, 0.58), (0.50, 0.46), (0.50, 0.38), (0.50, 0.30)] \
        + [(0.60, 0.60), (0.62, 0.48), (0.63, 0.40), (0.64, 0.32)] \
        + [(0.68, 0.62), (0.71, 0.52), (0.72, 0.46), (0.73, 0.40)]
    total = 0
    for i in range(60):
        ev = gc.evaluate_frame({"L": lm}, s, i / 30)
        total += len(ev)
    assert total == 0  # 静止手绝不触发
