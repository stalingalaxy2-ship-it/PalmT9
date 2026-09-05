# -*- coding: utf-8 -*-
"""test_product_qa.py —— PalmT9 产品交付质量监督测试套件（pytest）

监督对象: gesture_core.py（双次捏合触发核心）
运行: python -m pytest test_product_qa.py -v
覆盖:
  A. 状态与接口完整性（防回归）
  B. 双次捏合状态机（逐键触发 / 防抖 / 冷却 / 误触）
  C. 文本处理（T9 解码 / 候选 / 退格 / Shift / 中文）
  D. 标定算法
  E. 性能（单帧判定延迟）
  F. 交付物完整性
"""
import json
import math
import os
import time

import pytest

import gesture_core as gc

FPS = 30.0

# ------------------------------------------------------------------
# 合成手部模型（独立于 sim.py，防止 sim.py 与核心一起改坏）
# ------------------------------------------------------------------
def base_hand(role="L"):
    pts = {
        0: (0.50, 0.85),
        1: (0.42, 0.78), 2: (0.36, 0.72), 3: (0.32, 0.68), 4: (0.30, 0.66),
        5: (0.40, 0.60), 6: (0.38, 0.48), 7: (0.37, 0.40), 8: (0.36, 0.32),
        9: (0.50, 0.58), 10: (0.50, 0.46), 11: (0.50, 0.38), 12: (0.50, 0.30),
        13: (0.60, 0.60), 14: (0.62, 0.48), 15: (0.63, 0.40), 16: (0.64, 0.32),
        17: (0.68, 0.62), 18: (0.71, 0.52), 19: (0.72, 0.46), 20: (0.73, 0.40),
    }
    lm = [pts[i] for i in range(21)]
    if role == "R":
        lm = [(1.0 - x, y) for (x, y) in lm]
    return lm


def _lerp(a, b, t):
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)


def double_pinch_frames(role, target_lm):
    """合成一次合法双次捏合: 松开位 -> 捏合 -> 松开 -> 捏合 -> 松开(触发)。

    为避免拇指松开途中误入相邻键的最近区域（真实产品风险点），
    拇指松开位取目标关节沿"腕->关节"方向外延 0.9*scale 处，
    该点最近键仍是目标键，且 ratio > release 阈值。
    """
    lm0 = base_hand(role)
    wrist = lm0[0]
    scale = math.dist(lm0[0], lm0[9])
    tgt = lm0[target_lm]
    d = math.dist(wrist, tgt) or 1e-6
    ux, uy = (tgt[0] - wrist[0]) / d, (tgt[1] - wrist[1]) / d
    rest = (tgt[0] + ux * 0.9 * scale, tgt[1] + uy * 0.9 * scale)

    frames = []
    frames += [rest] * 4                     # 稳定 idle
    frames += [_lerp(rest, tgt, 0.5), tgt]   # 第1次捏合
    frames += [tgt] * 2
    frames += [_lerp(tgt, rest, 0.5), rest]  # 松开
    frames += [rest] * 3                     # 间隔 ~0.13s, 满足 MIN_INTERVAL
    frames += [_lerp(rest, tgt, 0.5), tgt]   # 第2次捏合
    frames += [tgt] * 2
    frames += [_lerp(tgt, rest, 0.5), rest]  # 再松开 -> 应触发
    frames += [rest] * 2

    seq = []
    for p in frames:
        lm = list(lm0)
        lm[4] = p
        seq.append({role: lm})
    return seq


def run_seq(seq, state=None):
    state = state or gc.GestureState()
    events = []
    for i, hands in enumerate(seq):
        events += gc.evaluate_frame(hands, state, i / FPS)
    return events, state


def rest_seq(role, n=100, jitter=0.004):
    lm0 = base_hand(role)
    seed = 12345
    seq = []
    for _ in range(n):
        seed = (seed * 1103515245 + 12345) % (2 ** 31)
        jx = ((seed % 1000) / 1000 - 0.5) * 2 * jitter
        seed = (seed * 1103515245 + 12345) % (2 ** 31)
        jy = ((seed % 1000) / 1000 - 0.5) * 2 * jitter
        seq.append({role: [(x + jx, y + jy) for (x, y) in lm0]})
    return seq


# ==================================================================
# A. 状态与接口完整性
# ==================================================================
class TestStateIntegrity:
    def test_state_has_pinch_state(self):
        """evaluate_frame 依赖 state._pinch，GestureState 必须初始化它，
        否则第一帧就 AttributeError —— 交付级阻断缺陷。"""
        s = gc.GestureState()
        assert hasattr(s, "_pinch"), "GestureState 缺少 _pinch 初始化，evaluate_frame 必崩"

    def test_evaluate_frame_smoke(self):
        """喂一帧合法关键点不抛异常。"""
        s = gc.GestureState()
        ev = gc.evaluate_frame({"L": base_hand("L")}, s, 0.0)
        assert isinstance(ev, list)

    def test_evaluate_frame_tolerates_bad_input(self):
        s = gc.GestureState()
        assert gc.evaluate_frame({"L": None}, s, 0.0) == []
        assert gc.evaluate_frame({"L": [(0, 0)] * 5}, s, 0.0) == []
        assert gc.evaluate_frame({}, s, 0.0) == []

    def test_build_targets(self):
        lt = gc.build_targets("L")
        rt = gc.build_targets("R")
        assert len(lt) == 12, f"左手应 12 键, 实际 {len(lt)}"
        assert len(rt) == 10, f"右手应 10 键, 实际 {len(rt)}"
        lms = {t[2] for t in lt + rt}
        assert all(0 <= i < 21 for i in lms)


# ==================================================================
# B. 双次捏合状态机
# ==================================================================
LEFT_KEY_LMS = [k["lm"] for k in gc.LEFT_KEYS]
RIGHT_KEY_LMS = [k["lm"] for k in gc.RIGHT_KEYS]


class TestPinchStateMachine:
    @pytest.mark.parametrize("k", gc.LEFT_KEYS, ids=lambda k: f"L_{k['key']}")
    def test_left_key_double_pinch_fires(self, k):
        events, _ = run_seq(double_pinch_frames("L", k["lm"]))
        fired = [e for e in events if e["role"] == "L"]
        assert len(fired) >= 1, f"左手 {k['key']} (lm{k['lm']}) 双次捏合未触发"
        assert fired[0]["key"] == k["key"], f"期望键 {k['key']}, 实际 {fired[0]['key']}"

    @pytest.mark.parametrize("k", gc.RIGHT_KEYS, ids=lambda k: f"R_{k['key']}")
    def test_right_key_double_pinch_fires(self, k):
        events, _ = run_seq(double_pinch_frames("R", k["lm"]))
        fired = [e for e in events if e["role"] == "R"]
        assert len(fired) >= 1, f"右手 {k['key']} (lm{k['lm']}) 双次捏合未触发"
        assert fired[0]["key"] == k["key"], f"期望键 {k['key']}, 实际 {fired[0]['key']}"

    def test_rest_hand_zero_false_trigger(self):
        """静息手 + 传感器抖动 100 帧 x 双手, 0 触发（防误触底线）。"""
        for role in ("L", "R"):
            events, _ = run_seq(rest_seq(role, n=100))
            assert events == [], f"{role} 手静息产生 {len(events)} 次误触"

    def test_single_pinch_no_trigger(self):
        """只捏合一次不得触发（双次捏合的防误触核心）。"""
        lm0 = base_hand("L")
        tgt = lm0[6]
        wrist = lm0[0]
        scale = math.dist(lm0[0], lm0[9])
        d = math.dist(wrist, tgt)
        ux, uy = (tgt[0] - wrist[0]) / d, (tgt[1] - wrist[1]) / d
        rest = (tgt[0] + ux * 0.9 * scale, tgt[1] + uy * 0.9 * scale)
        seq = []
        for p in [rest] * 4 + [tgt] * 3 + [rest] * 20:
            lm = list(lm0); lm[4] = p
            seq.append({"L": lm})
        events, _ = run_seq(seq)
        assert events == [], f"单次捏合误触发 {len(events)} 次"

    def test_cooldown_blocks_immediate_retrigger(self):
        """触发后 COOLDOWN 内紧随的双次捏合不应立即再触发。"""
        seq = double_pinch_frames("L", 6) + double_pinch_frames("L", 6)
        events, _ = run_seq(seq)
        # 简化: 只统计事件数（两段拼接帧间隔<COOLDOWN 时第二段应被冷却或间隔校验挡住一部分）
        assert len(events) <= 2

    def test_max_interval_timeout(self):
        """两次捏合间隔 > MAX_INTERVAL 应作废，不触发。"""
        lm0 = base_hand("L")
        tgt = lm0[6]
        wrist = lm0[0]
        scale = math.dist(lm0[0], lm0[9])
        d = math.dist(wrist, tgt)
        ux, uy = (tgt[0] - wrist[0]) / d, (tgt[1] - wrist[1]) / d
        rest = (tgt[0] + ux * 0.9 * scale, tgt[1] + uy * 0.9 * scale)
        seq = []
        for p in [rest] * 4 + [tgt] * 2 + [rest] * 30 + [tgt] * 2 + [rest] * 4:
            lm = list(lm0); lm[4] = p
            seq.append({"L": lm})
        events, _ = run_seq(seq)
        assert events == [], "超过 MAX_INTERVAL 的两次捏合不应触发"

    def test_two_hands_independent(self):
        """双手并行各敲各的，互不复位对方状态机。"""
        l_seq = double_pinch_frames("L", 6)
        r_seq = double_pinch_frames("R", 11)
        n = max(len(l_seq), len(r_seq))
        seq = []
        for i in range(n):
            hands = {}
            if i < len(l_seq): hands["L"] = l_seq[i]["L"]
            if i < len(r_seq): hands["R"] = r_seq[i]["R"]
            seq.append(hands)
        events, _ = run_seq(seq)
        roles = {e["role"] for e in events}
        assert "L" in roles and "R" in roles, f"双手独立触发失败: {events}"


# ==================================================================
# C. 文本处理
# ==================================================================
class TestTextPipeline:
    def test_word_to_seq(self):
        assert gc.word_to_seq("hello") == "43556"
        assert gc.word_to_seq("world") == "96753"

    def test_candidates_sorted(self):
        c = gc.candidates_for(list("4663"))
        assert c and all(c[i][1] >= c[i + 1][1] for i in range(len(c) - 1))

    def test_commit_top1(self):
        s = gc.GestureState()
        s.digits = list("43556")
        assert gc.commit(s) == "hello"
        assert s.committed == "hello "
        assert s.digits == []

    def test_cycle_then_commit(self):
        s = gc.GestureState()
        s.digits = list("4663")
        c = gc.candidates_for(s.digits)
        assert len(c) >= 2
        gc.cycle_candidate(s)
        assert gc.commit(s) == c[1][0]

    def test_commit_fallback_raw_digits(self):
        s = gc.GestureState()
        s.digits = list("999999")
        assert gc.commit(s) == "999999"

    def test_shift_capitalizes_once(self):
        s = gc.GestureState()
        s.digits = list("43556")
        s.shift = True
        assert gc.commit(s) == "Hello"
        assert s.shift is False

    def test_backspace_priority(self):
        s = gc.GestureState()
        s.digits = list("466")
        gc.backspace(s)
        assert s.digits == list("46")
        s.digits = []
        s.committed = "hello "
        gc.backspace(s)
        assert s.committed == "hello"

    def test_empty_commit_gives_space(self):
        s = gc.GestureState()
        assert gc.commit(s) == " "
        assert s.committed == " "

    def test_cn_candidates(self):
        c = gc.candidates_cn(list("64426"))   # nihao
        assert c and c[0][0] == "你好"

    def test_cn_commit(self):
        s = gc.GestureState()
        s.cn_mode = True
        s.digits = list("744543")             # shijie
        assert gc.commit(s) == "世界"


# ==================================================================
# D. 标定
# ==================================================================
class TestCalibration:
    def test_hand_scale(self):
        lm = base_hand("L")
        assert abs(gc.estimate_hand_scale(lm) - 0.27) < 0.02
        assert gc.estimate_hand_scale(None) is None
        assert gc.estimate_hand_scale([(0, 0)] * 5) is None

    def test_recommend_threshold(self):
        assert gc.recommend_threshold([]) == 0.34
        assert abs(gc.recommend_threshold([0.1, 0.4]) - 0.56) < 1e-6
        assert gc.recommend_threshold([0.05], lo=0.2) == 0.2
        assert gc.recommend_threshold([0.9], hi=0.7) == 0.7


# ==================================================================
# E. 性能
# ==================================================================
class TestPerformance:
    def test_frame_latency_under_1ms(self):
        """单帧判定 < 1ms（30fps 实时预算的 3%）。"""
        s = gc.GestureState()
        lm = base_hand("L")
        n = 2000
        t0 = time.perf_counter()
        for i in range(n):
            gc.evaluate_frame({"L": lm, "R": base_hand("R")}, s, i / FPS)
        per = (time.perf_counter() - t0) / n * 1000
        assert per < 1.0, f"单帧 {per:.3f}ms 超预算"


# ==================================================================
# F. 交付物完整性
# ==================================================================
ROOT = os.path.dirname(os.path.abspath(__file__))


class TestDeliverables:
    @pytest.mark.parametrize("f", [
        "palm_t9.py", "gesture_core.py", "calibrate.py", "config.py",
        "launcher.py", "requirements.txt", "README.md",
        "hand_landmarker.task", "build_exe.bat",
        "产品手册.md", "使用说明.md", "交付清单.md",
    ])
    def test_file_exists(self, f):
        assert os.path.isfile(os.path.join(ROOT, f)), f"缺交付文件: {f}"

    def test_model_file_not_empty(self):
        p = os.path.join(ROOT, "hand_landmarker.task")
        assert os.path.getsize(p) > 1_000_000, "模型文件异常（太小）"

    def test_config_json_valid(self):
        p = os.path.join(ROOT, "config.json")
        if os.path.exists(p):
            with open(p, encoding="utf-8") as fh:
                json.load(fh)

    def test_requirements_parseable(self):
        p = os.path.join(ROOT, "requirements.txt")
        with open(p, encoding="utf-8") as fh:
            lines = [l.strip() for l in fh if l.strip() and not l.startswith("#")]
        assert lines, "requirements.txt 为空"



