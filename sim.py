# -*- coding: utf-8 -*-
"""
sim.py —— PalmT9 无头仿真测试基座（无摄像头）
==============================================
用合成手部 21 关键点轨迹喂给 gesture_core.evaluate_frame，
客观测量: 触发率(TPR) / 误触率(FPR) / 逐键可触率 / 端到端盲打 / 延迟。

用法:
    python sim.py            # 跑基线, 打印 metrics.json
"""
import json
import sys
import time

import gesture_core as gc

# Windows 控制台 GBK, 强制 UTF-8 防止 ✓/✗ 崩溃
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


# ---------------- 合成手部模型 ----------------
def base_hand(role):
    """返回 21 个 (x,y) 归一化关键点。左手掌心朝上; 右手做 x 镜像。"""
    pts = {
        0: (0.50, 0.85),                      # 腕部
        1: (0.42, 0.78), 2: (0.36, 0.72), 3: (0.32, 0.68),  # 拇指根->IP
        4: (0.30, 0.66),                      # 拇指尖(静息)
        5: (0.40, 0.60), 6: (0.38, 0.48), 7: (0.37, 0.40), 8: (0.36, 0.32),   # 食指
        9: (0.50, 0.58), 10: (0.50, 0.46), 11: (0.50, 0.38), 12: (0.50, 0.30),  # 中指
        13: (0.60, 0.60), 14: (0.62, 0.48), 15: (0.63, 0.40), 16: (0.64, 0.32),  # 无名指
        17: (0.68, 0.62), 18: (0.71, 0.52), 19: (0.72, 0.46), 20: (0.73, 0.40),  # 小指
    }
    lm = [pts[i] for i in range(21)]
    if role == "R":
        lm = [(1.0 - x, y) for (x, y) in lm]
    return lm


def _lerp(a, b, t):
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)


def tap_frames(role, target_lm, n_jump=2, n_hold=3):
    """真实敲击: 拇指从静息快速跳到目标关节(1-2帧), 然后停留。
    快速跳变让速度门能测到'敲', 又不会慢慢滑过相邻键。"""
    lm0 = base_hand(role)
    rest = lm0[4]
    target = lm0[target_lm]
    frames = []
    # 快速跳变: 静息 -> 目标, 分 n_jump 帧(位移大=速度快)
    for i in range(n_jump):
        t = (i + 1) / n_jump
        lm = list(lm0)
        lm[4] = _lerp(rest, target, t)
        frames.append(lm)
    # 停留
    for _ in range(n_hold):
        lm = list(lm0)
        lm[4] = target
        frames.append(lm)
    return frames


def rest_frames(role, n=100, jitter=0.004):
    """静息手 + 微小确定性抖动(模拟传感器噪声), 测误触。"""
    lm0 = base_hand(role)
    frames = []
    seed = 12345
    for i in range(n):
        # 简单确定性伪随机抖动
        seed = (seed * 1103515245 + 12345) % (2 ** 31)
        jx = ((seed % 1000) / 1000 - 0.5) * 2 * jitter
        seed = (seed * 1103515245 + 12345) % (2 ** 31)
        jy = ((seed % 1000) / 1000 - 0.5) * 2 * jitter
        lm = [(x + jx, y + jy) for (x, y) in lm0]
        frames.append(lm)
    return frames


# ---------------- 测试执行 ----------------
FPS = 30.0


def run_frames(hands_seq):
    """hands_seq: 每帧 dict role->lm; 返回 (events, committed)"""
    state = gc.GestureState()
    events = []
    for idx, hands in enumerate(hands_seq):
        now = idx / FPS
        ev = gc.evaluate_frame(hands, state, now)
        events.extend(ev)
    return events, state.committed


def one_hand(role, lm):
    return {role: lm}


def test_tpr():
    """每个键单独敲一次, 是否触发正确的键。"""
    results = {}
    # 左手字母键 + 空格/退格
    for k in gc.LEFT_LETTERS:
        seq = [one_hand("L", lm) for lm in tap_frames("L", k["lm"])]
        events, _ = run_frames(seq)
        fired = [e for e in events if e["kind"] == "letter" and e["payload"] == k["digit"]]
        results[f"L_letter_{k['digit']}"] = len(fired) > 0
    for name, lm, kind in [("L_space", gc.LEFT_SPACE["lm"], "space"),
                           ("L_back", gc.LEFT_BACK["lm"], "back"),
                           ("L_cycle", gc.LEFT_CYCLE["lm"], "cycle")]:
        seq = [one_hand("L", lm) for lm in tap_frames("L", lm)]
        events, _ = run_frames(seq)
        fired = [e for e in events if e["kind"] == kind]
        results[name] = len(fired) > 0
    # 右手数字键 + 0 + 符号 + 大小写
    for k in gc.RIGHT_DIGITS:
        seq = [one_hand("R", lm) for lm in tap_frames("R", k["lm"])]
        events, _ = run_frames(seq)
        fired = [e for e in events if e["kind"] == "digit" and e["payload"] == k["digit"]]
        results[f"R_digit_{k['digit']}"] = len(fired) > 0
    seq = [one_hand("R", lm) for lm in tap_frames("R", gc.RIGHT_ZERO["lm"])]
    events, _ = run_frames(seq)
    results["R_digit_0"] = any(e["kind"] == "digit" and e["payload"] == "0" for e in events)
    seq = [one_hand("R", lm) for lm in tap_frames("R", gc.RIGHT_SYM["lm"])]
    events, _ = run_frames(seq)
    results["R_symbol"] = any(e["kind"] == "symbol" for e in events)
    seq = [one_hand("R", lm) for lm in tap_frames("R", gc.RIGHT_SHIFT["lm"])]
    events, _ = run_frames(seq)
    results["R_shift"] = any(e["kind"] == "shift" for e in events)
    return results


def test_fpr():
    """静息手不应触发任何键。"""
    total_events = 0
    for role in ("L", "R"):
        seq = [one_hand(role, lm) for lm in rest_frames(role, n=100)]
        events, _ = run_frames(seq)
        total_events += len(events)
    return total_events


def rest_frame(role):
    return base_hand(role)


def _letter_lm(digit):
    for k in gc.LEFT_LETTERS:
        if k["digit"] == digit:
            return k["lm"]
    return None


def test_e2e_hello():
    """盲打 hello: 4,3,5,5,6 再敲左手小指尖(空格)。"""
    seq_lms = []
    taps = [("4", 7), ("3", 16), ("5", 11), ("5", 11), ("6", 15)]
    for i, (digit, lm) in enumerate(taps):
        seq_lms += tap_frames("L", lm)
        seq_lms += [rest_frame("L")] * 12
    seq_lms += tap_frames("L", gc.LEFT_SPACE["lm"])
    seq = [one_hand("L", lm) for lm in seq_lms]
    _, committed = run_frames(seq)
    return committed


def test_e2e_shift_hello():
    """shift 后盲打 hello -> 'Hello '。"""
    seq = []
    seq += [one_hand("R", lm) for lm in tap_frames("R", gc.RIGHT_SHIFT["lm"])]
    seq += [one_hand("R", rest_frame("R"))] * 12
    for digit in ["4", "3", "5", "5", "6"]:
        seq += [one_hand("L", lm) for lm in tap_frames("L", _letter_lm(digit))]
        seq += [one_hand("L", rest_frame("L"))] * 12
    seq += [one_hand("L", lm) for lm in tap_frames("L", gc.LEFT_SPACE["lm"])]
    _, committed = run_frames(seq)
    return committed


def test_e2e_cycle_second():
    """4663 首候选 home, 切一次候选应出第二候选。"""
    seq = []
    for digit in ["4", "6", "6", "3"]:
        seq += [one_hand("L", lm) for lm in tap_frames("L", _letter_lm(digit))]
        seq += [one_hand("L", rest_frame("L"))] * 12
    seq += [one_hand("L", lm) for lm in tap_frames("L", gc.LEFT_CYCLE["lm"])]
    seq += [one_hand("L", rest_frame("L"))] * 12
    seq += [one_hand("L", lm) for lm in tap_frames("L", gc.LEFT_SPACE["lm"])]
    _, committed = run_frames(seq)
    return committed


def test_e2e_cn_nihao():
    """中文模式盲打 nihao(6,4,4,2,6) -> '你好 '。"""
    state = gc.GestureState()
    state.cn_mode = True
    seq = []
    for digit in ["6", "4", "4", "2", "6"]:
        seq += [one_hand("L", lm) for lm in tap_frames("L", _letter_lm(digit))]
        seq += [one_hand("L", rest_frame("L"))] * 12
    seq += [one_hand("L", lm) for lm in tap_frames("L", gc.LEFT_SPACE["lm"])]
    events = []
    for idx, hands in enumerate(seq):
        events += gc.evaluate_frame(hands, state, idx / FPS)
    return state.committed


def test_latency(n=1000):
    state = gc.GestureState()
    lm = base_hand("L")
    t0 = time.perf_counter()
    for i in range(n):
        gc.evaluate_frame({"L": lm}, state, i / FPS)
    return (time.perf_counter() - t0) / n * 1000  # ms


def main():
    tpr = test_tpr()
    tpr_pass = sum(1 for v in tpr.values() if v)
    fpr_events = test_fpr()
    hello = test_e2e_hello()
    shift_hello = test_e2e_shift_hello()
    cycle_second = test_e2e_cycle_second()
    cn_nihao = test_e2e_cn_nihao()
    lat = test_latency()

    metrics = {
        "tpr_per_key": tpr,
        "tpr_pass": tpr_pass,
        "tpr_total": len(tpr),
        "tpr_rate": round(tpr_pass / len(tpr), 3),
        "fpr_rest_events": fpr_events,
        "e2e_hello_committed": hello,
        "e2e_hello_ok": hello.strip() == "hello",
        "e2e_shift_hello": shift_hello,
        "e2e_shift_ok": shift_hello.strip() == "Hello",
        "e2e_cycle_second": cycle_second,
        "e2e_cn_nihao": cn_nihao,
        "e2e_cn_ok": cn_nihao.strip() == "你好",
        "latency_ms": round(lat, 3),
    }
    with open("metrics.json", "w", encoding="utf-8") as f:
        json.dump(metrics, f, ensure_ascii=False, indent=2)

    print("=== PalmT9 仿真基线 ===")
    print(f"逐键触发 TPR: {tpr_pass}/{len(tpr)}  (rate={metrics['tpr_rate']})")
    for k, v in tpr.items():
        if not v:
            print(f"   ✗ 未触发: {k}")
    print(f"静息误触 FPR 事件数: {fpr_events}  (期望 0)")
    print(f"端到端 hello: '{hello}'  (ok={metrics['e2e_hello_ok']})")
    print(f"端到端 shift+hello: '{shift_hello}'  (ok={metrics['e2e_shift_ok']})")
    print(f"端到端 候选切换第二: '{cycle_second}'")
    print(f"端到端 中文 nihao: '{cn_nihao}'  (ok={metrics['e2e_cn_ok']})")
    print(f"单帧延迟: {lat:.3f} ms")
    print("已写入 metrics.json")


if __name__ == "__main__":
    main()
