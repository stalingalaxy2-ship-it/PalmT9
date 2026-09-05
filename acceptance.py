# -*- coding: utf-8 -*-
"""
PalmT9 视觉验收工具  acceptance.py（双手自敲版）
================================================
自动完成一整套「视觉验收」，跑完自动打 PASS/FAIL 并生成 acceptance_report.txt。

用法:
    python acceptance.py        # 确保同目录有 hand_landmarker.task
操作:
    按屏幕中文提示做动作; 随时按 ESC 中止并输出已完成项报告。

验收项目:
    1. 摄像头与帧率      2. 手检测率(双手)    3. 关键点稳定性(抖动)
    4. 全键逐键触发(左字母9 + 右数字9 + 功能键)
    5. 端到端盲打 hello   6. 单帧处理延迟
"""
import math
import os
import statistics
import sys
import time

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import cv2
import numpy as np
import mediapipe as mp
from mediapipe.tasks.python import vision
from mediapipe.tasks.python.core.base_options import BaseOptions

import palm_t9  # 复用 LEFT_LETTERS/RIGHT_DIGITS/功能键/State/candidates_for/click

MODEL_PATH = "hand_landmarker.task"
WINDOW = "PalmT9 验收"

# ---------------- 中文绘制(PIL) ----------------
from PIL import Image, ImageDraw, ImageFont

_FONT_PATHS = [r"C:\Windows\Fonts\msyh.ttc",
               r"C:\Windows\Fonts\simhei.ttf",
               r"C:\Windows\Fonts\simsun.ttc"]
_font_cache = {}


def _get_font(size):
    if size in _font_cache:
        return _font_cache[size]
    for p in _FONT_PATHS:
        if os.path.exists(p):
            try:
                f = ImageFont.truetype(p, size)
                _font_cache[size] = f
                return f
            except Exception:
                continue
    _font_cache[size] = None
    return None


def draw_cn(frame, text, pos, size=26, color=(255, 255, 255), stroke=(0, 0, 0)):
    font = _get_font(size)
    if font is None:
        cv2.putText(frame, text, pos, cv2.FONT_HERSHEY_SIMPLEX,
                    0.8, color, 2, cv2.LINE_AA)
        return frame
    img = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
    d = ImageDraw.Draw(img)
    d.text(pos, text, font=font, fill=(color[2], color[1], color[0]),
           stroke_width=2, stroke_fill=(stroke[2], stroke[1], stroke[0]))
    return cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)


# ---------------- 视觉工具 ----------------
def make_landmarker():
    options = vision.HandLandmarkerOptions(
        base_options=BaseOptions(model_asset_path=MODEL_PATH),
        running_mode=vision.RunningMode.VIDEO,
        num_hands=2,
        min_hand_detection_confidence=0.6,
        min_hand_presence_confidence=0.5,
        min_tracking_confidence=0.5,
    )
    return vision.HandLandmarker.create_from_options(options)


def detect_roles(landmarker, frame):
    """按屏幕 x 排序: 屏幕左=字母手(L), 屏幕右=数字手(R)。返回 roles dict。"""
    h, w = frame.shape[:2]
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    img = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
    ts = int(time.monotonic() * 1000)
    res = landmarker.detect_for_video(img, ts)
    roles = {}
    if res.hand_landmarks:
        detected = sorted(res.hand_landmarks, key=lambda lm: lm[0].x)
        if len(detected) >= 2:
            roles["L"], roles["R"] = detected[0], detected[1]
        elif len(detected) == 1:
            roles["L" if detected[0][0].x * w < w / 2 else "R"] = detected[0]
    return roles


def px(lm, i, w, h):
    return (int(lm[i].x * w), int(lm[i].y * h))


def hand_scale(lm, w, h):
    a = px(lm, 0, w, h)
    b = px(lm, 9, w, h)
    return math.hypot(a[0] - b[0], a[1] - b[1]) or 1.0


def ratio_to(lm, w, h, target_lm):
    """该手自身拇指(4)到目标关节的距离比(双手自敲: 各自拇指敲各自键)。"""
    t = px(lm, 4, w, h)
    p = px(lm, target_lm, w, h)
    return math.hypot(t[0] - p[0], t[1] - p[1]) / hand_scale(lm, w, h)


def draw_skeleton(frame, lm):
    vision.drawing_utils.draw_landmarks(
        frame, lm, vision.HandLandmarksConnections.HAND_CONNECTIONS)


# ---------------- 通用窗口驱动 ----------------
def run_window(cap, landmarker, duration, title, collect=None):
    """collect(roles, frame)->any 每帧调用; 返回样本列表; ESC 返回 None。"""
    samples = []
    t0 = time.time()
    while True:
        el = time.time() - t0
        if el >= duration:
            break
        ok, frame = cap.read()
        if not ok:
            continue
        frame = cv2.flip(frame, 1)
        roles = detect_roles(landmarker, frame)
        if collect is not None:
            samples.append(collect(roles, frame))
        title_text = title() if callable(title) else title
        frame = draw_cn(frame, title_text, (16, 12), size=30, color=(0, 255, 255))
        remaining = max(0.0, duration - el)
        frame = draw_cn(frame, f"剩余 {remaining:.1f}s", (16, 48),
                        size=24, color=(0, 200, 255))
        cv2.imshow(WINDOW, frame)
        if cv2.waitKey(1) & 0xFF == 27:
            return None
    return samples


def wait_ready(cap, landmarker, msg):
    while True:
        ok, frame = cap.read()
        if not ok:
            continue
        frame = cv2.flip(frame, 1)
        frame = draw_cn(frame, msg, (16, 200), size=28, color=(0, 255, 0))
        frame = draw_cn(frame, "准备好后按任意键开始 (ESC 退出)",
                        (16, 250), size=22, color=(0, 200, 255))
        cv2.imshow(WINDOW, frame)
        k = cv2.waitKey(1) & 0xFF
        if k == 27:
            return False
        if k != 255:
            return True


# ---------------- 各验收项 ----------------
def stage_camera(cap, landmarker):
    title = "验收 1/6 摄像头与帧率(无需动作)"
    n = 0
    t0 = time.time()
    while time.time() - t0 < 3.0:
        ok, frame = cap.read()
        if not ok:
            return {"name": "摄像头与帧率", "passed": False,
                    "metrics": {"frames": n},
                    "note": "无法读取摄像头帧",
                    "suggestion": "检查摄像头连接/是否被其他程序占用"}
        frame = cv2.flip(frame, 1)
        n += 1
        frame = draw_cn(frame, title, (16, 12), size=28, color=(0, 255, 255))
        cv2.imshow(WINDOW, frame)
        if cv2.waitKey(1) & 0xFF == 27:
            return None
    fps = n / 3.0
    passed = fps >= 10.0
    return {"name": "摄像头与帧率", "passed": passed,
            "metrics": {"fps": round(fps, 1), "frames": n},
            "note": "" if passed else "帧率偏低",
            "suggestion": "" if passed else "降低分辨率/检查 USB 带宽"}


def stage_detect(cap, landmarker):
    def collect(roles, frame):
        return len(roles)
    samples = run_window(cap, landmarker, 4.0,
                         "验收 2/6 双手掌心朝上,五指张开",
                         collect=collect)
    if samples is None:
        return None
    two = sum(1 for s in samples if s >= 2)
    any_hand = sum(1 for s in samples if s >= 1)
    rate2 = two / len(samples) if samples else 0.0
    rate1 = any_hand / len(samples) if samples else 0.0
    passed = rate1 >= 0.6
    return {"name": "手检测率", "passed": passed,
            "metrics": {"single_hand_rate": round(rate1, 2),
                        "two_hand_rate": round(rate2, 2)},
            "note": "" if passed else "检出率低",
            "suggestion": "" if passed else "增加光照/减少背景杂乱/双手分开"}


def stage_jitter(cap, landmarker):
    def collect(roles, frame):
        lm = roles.get("L") or roles.get("R")
        if not lm:
            return None
        return px(lm, 12, frame.shape[1], frame.shape[0])
    samples = run_window(cap, landmarker, 4.0,
                         "验收 3/6 手保持静止不动(测抖动)",
                         collect=collect)
    if samples is None:
        return None
    pts = [s for s in samples if s]
    if len(pts) < 10:
        return {"name": "关键点稳定性", "passed": False,
                "metrics": {"samples": len(pts)},
                "note": "有效样本过少", "suggestion": "先解决手检测率"}
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    jitter = round(max(statistics.pstdev(xs), statistics.pstdev(ys)), 2)
    passed = jitter <= 8.0
    return {"name": "关键点稳定性(中指尖抖动px)", "passed": passed,
            "metrics": {"jitter_px": jitter, "samples": len(pts)},
            "note": "" if passed else "抖动过大",
            "suggestion": "" if passed else "手放稳/提升光照/固定摄像头"}


def _all_targets():
    """返回 [(hand, kind, label, lm), ...] 覆盖全部键。"""
    t = []
    for k in palm_t9.LEFT_LETTERS:
        t.append(("L", "letter", k["digit"], k["lm"]))
    for k in palm_t9.RIGHT_DIGITS:
        t.append(("R", "digit", k["digit"], k["lm"]))
    t.append(("L", "space", "空格", palm_t9.LEFT_SPACE["lm"]))
    t.append(("L", "back", "退格", palm_t9.LEFT_BACK["lm"]))
    t.append(("L", "cycle", "换候选", palm_t9.LEFT_CYCLE["lm"]))
    t.append(("R", "digit", "0", palm_t9.RIGHT_ZERO["lm"]))
    t.append(("R", "symbol", "符号", palm_t9.RIGHT_SYM["lm"]))
    t.append(("R", "shift", "大小写", palm_t9.RIGHT_SHIFT["lm"]))
    return t


def stage_keys(cap, landmarker):
    st = palm_t9.State()
    threshold = st.threshold
    per_key = []
    for hand, kind, label, lm in _all_targets():
        hold = {"min_ratio": 1e9, "triggered": False,
                "hand": hand, "label": label}

        def collect(roles, frame, hold=hold, hand=hand, lm=lm):
            target = roles.get(hand)
            if not target:
                return None
            w, hh = frame.shape[1], frame.shape[0]
            r = ratio_to(target, w, hh, lm)
            hold["min_ratio"] = min(hold["min_ratio"], r)
            if r < threshold:
                hold["triggered"] = True
            p = px(target, lm, w, hh)
            cv2.circle(frame, p, 16, (0, 255, 255), 3)
            draw_skeleton(frame, target)
            return r

        side = "左手" if hand == "L" else "右手"
        samples = run_window(cap, landmarker, 3.0,
                             f"验收 4/6 {side}敲 [{label}]",
                             collect=collect)
        if samples is None:
            return None
        per_key.append(hold)

    triggered_n = sum(1 for x in per_key if x["triggered"])
    passed = triggered_n >= len(per_key) - 4  # 共 24 键, 容差 4
    return {"name": "全键逐键触发覆盖", "passed": passed,
            "metrics": {"triggered": triggered_n, "of": len(per_key),
                        "threshold": threshold},
            "per_key": per_key,
            "note": "" if passed else f"仅 {triggered_n}/{len(per_key)} 键可触发",
            "suggestion": "" if passed else "看 per_key 明细, 针对未触发键调阈值/位置"}


def stage_e2e(cap, landmarker):
    """引导盲打 hello: 4,3,5,5,6(全在左手字母键), 然后敲左小指尖提交。"""
    st = palm_t9.State()
    expect = ["4", "3", "5", "5", "6"]
    label_of = {k["digit"]: (k["lm"],) for k in palm_t9.LEFT_LETTERS}
    steps = []

    for i, d in enumerate(expect, 1):
        lm = label_of[d][0]
        hit = {"ok": False}

        def collect(roles, frame, lm=lm, hit=hit):
            target = roles.get("L")
            if not target:
                return None
            w, hh = frame.shape[1], frame.shape[0]
            r = ratio_to(target, w, hh, lm)
            if r < st.threshold:
                hit["ok"] = True
            p = px(target, lm, w, hh)
            cv2.circle(frame, p, 18, (0, 255, 255), 3)
            draw_skeleton(frame, target)
            return r

        samples = run_window(cap, landmarker, 6.0,
                             f"验收 5/6 第{i}/6步: 左手敲 [{d}]",
                             collect=collect)
        if samples is None:
            return None
        steps.append({"step": i, "digit": d, "hit": hit["ok"]})

    space_hit = {"ok": False}

    def collect_space(roles, frame):
        target = roles.get("L")
        if not target:
            return None
        w, hh = frame.shape[1], frame.shape[0]
        r = ratio_to(target, w, hh, palm_t9.LEFT_SPACE["lm"])
        if r < st.threshold:
            space_hit["ok"] = True
        p = px(target, palm_t9.LEFT_SPACE["lm"], w, hh)
        cv2.circle(frame, p, 18, (255, 255, 0), 3)
        draw_skeleton(frame, target)
        return r

    samples = run_window(cap, landmarker, 6.0,
                         "验收 5/6 最后: 左小指尖提交",
                         collect=collect_space)
    if samples is None:
        return None

    seq = "".join(s["digit"] for s in steps if s["hit"])
    cands = palm_t9.candidates_for(list(seq))
    top = cands[0][0] if cands else "(无候选)"
    passed = (seq == "43556" and top == "hello" and space_hit["ok"])
    return {"name": "端到端盲打 hello", "passed": passed,
            "metrics": {"steps": steps, "captured_seq": seq,
                        "expect_seq": "43556", "top_candidate": top,
                        "space_commit": space_hit["ok"]},
            "note": "" if passed else "盲打未命中",
            "suggestion": "" if passed else "看 steps 哪一步 hit=False"}


def stage_latency(cap, landmarker):
    times = []
    t0 = time.time()
    n = 0
    while time.time() - t0 < 3.0:
        ok, frame = cap.read()
        if not ok:
            continue
        frame = cv2.flip(frame, 1)
        s = time.perf_counter()
        detect_roles(landmarker, frame)
        times.append((time.perf_counter() - s) * 1000)
        n += 1
        frame = draw_cn(frame, "验收 6/6 测量处理延迟", (16, 12),
                        size=28, color=(0, 255, 255))
        cv2.imshow(WINDOW, frame)
        if cv2.waitKey(1) & 0xFF == 27:
            return None
    avg = statistics.mean(times) if times else 1e9
    passed = avg <= 100.0
    return {"name": "单帧处理延迟", "passed": passed,
            "metrics": {"avg_ms": round(avg, 1), "frames": n},
            "note": "" if passed else "处理过慢",
            "suggestion": "" if passed else "降低输入分辨率/关闭其他占CPU程序"}


# ---------------- 报告 ----------------
def write_report(results, path="acceptance_report.txt"):
    lines = ["PalmT9 视觉验收报告", "=" * 50,
             f"时间: {time.strftime('%Y-%m-%d %H:%M:%S')}",
             f"mediapipe: {mp.__version__}   opencv: {cv2.__version__}", ""]
    done = [r for r in results if r]
    passed_n = sum(1 for r in done if r["passed"])
    for i, r in enumerate(done, 1):
        mark = "PASS" if r["passed"] else "FAIL"
        lines.append(f"[{mark}] {i}. {r['name']}")
        lines.append(f"     指标: {r['metrics']}")
        if r.get("note"):
            lines.append(f"     说明: {r['note']}")
        if r.get("suggestion"):
            lines.append(f"     建议: {r['suggestion']}")
        if r.get("per_key"):
            lines.append("     逐键明细(最小距离比 / 是否触发):")
            for k in r["per_key"]:
                mr = k["min_ratio"]
                mrs = f"{mr:.3f}" if mr < 1e8 else "N/A"
                lines.append(f"        {k['hand']}手 {k['label']:<6} "
                             f"min_ratio={mrs:<7} "
                             f"{'OK' if k['triggered'] else '未触发'}")
        lines.append("")
    lines += ["-" * 50, f"总体: {passed_n}/{len(done)} 项通过", "",
              "把这份文件发给我, 我据此定位问题并改代码。"]
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return "\n".join(lines)


def main():
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("无法打开摄像头, 验收中止。")
        return
    landmarker = make_landmarker()
    results = []
    try:
        if not wait_ready(cap, landmarker, "PalmT9 视觉验收: 将按提示自动判分"):
            print("已退出。")
            return
        for stage in (stage_camera, stage_detect, stage_jitter,
                      stage_keys, stage_e2e, stage_latency):
            r = stage(cap, landmarker)
            if r is None:
                print("用户中止, 输出已完成项报告。")
                break
            results.append(r)
            mark = "PASS" if r["passed"] else "FAIL"
            print(f"[{mark}] {r['name']}  {r['metrics']}")
    finally:
        landmarker.close()
        cap.release()
        cv2.destroyAllWindows()

    report = write_report(results)
    print("\n" + report)
    print("\n报告已保存到 acceptance_report.txt")


if __name__ == "__main__":
    main()
