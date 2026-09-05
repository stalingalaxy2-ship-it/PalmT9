# -*- coding: utf-8 -*-
"""
calibrate.py —— PalmT9 一键标定
================================
引导用户完成一次标定, 自动算出最合适的触发阈值并写入 config.json,
之后 palm_t9.py 启动时自动加载, 免手动调参。

流程:
    1. 双手张开静置 2 秒 → 测手部尺度
    2. 逐个敲左手 9 个字母键 + 空格 + 退格 → 记录每个键最小距离比
    3. 用 recommend_threshold 算阈值 → 写入 config.json

用法:
    python calibrate.py
"""
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

import gesture_core as gc
import config as config_mod

MODEL_PATH = "hand_landmarker.task"
WINDOW = "PalmT9 标定"

# 中文字体
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


def draw_cn(frame, text, pos, size=26, color=(255, 255, 255)):
    font = _get_font(size)
    if font is None:
        cv2.putText(frame, text, pos, cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2)
        return frame
    img = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
    d = ImageDraw.Draw(img)
    d.text(pos, text, font=font, fill=(color[2], color[1], color[0]),
           stroke_width=2, stroke_fill=(0, 0, 0))
    return cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)


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


def ratio_to(lm, w, h, target_lm):
    a = px(lm, 0, w, h)
    b = px(lm, 9, w, h)
    scale = (lambda p, q: ((p[0]-q[0])**2 + (p[1]-q[1])**2) ** 0.5)(a, b) or 1.0
    t = px(lm, 4, w, h)
    p = px(lm, target_lm, w, h)
    return ((t[0]-p[0])**2 + (t[1]-p[1])**2) ** 0.5 / scale


def draw_skeleton(frame, lm):
    vision.drawing_utils.draw_landmarks(
        frame, lm, vision.HandLandmarksConnections.HAND_CONNECTIONS)


def run_tap(cap, landmarker, title, hand, lm_idx, duration=4.0):
    """引导敲一个键, 返回该键最小距离比(手始终检测不到则 None)。"""
    min_r = None
    t0 = time.time()
    while time.time() - t0 < duration:
        ok, frame = cap.read()
        if not ok:
            continue
        frame = cv2.flip(frame, 1)
        h, w = frame.shape[:2]
        roles = detect_roles(landmarker, frame)
        target = roles.get(hand)
        if target is not None:
            r = ratio_to(target, w, h, lm_idx)
            min_r = r if min_r is None else min(min_r, r)
            draw_skeleton(frame, target)
            p = px(target, lm_idx, w, h)
            cv2.circle(frame, p, 18, (0, 255, 255), 3)
        frame = draw_cn(frame, title, (16, 12), size=28, color=(0, 255, 255))
        remaining = max(0.0, duration - (time.time() - t0))
        frame = draw_cn(frame, f"剩余 {remaining:.1f}s  ESC 中止",
                        (16, 48), size=22, color=(0, 200, 255))
        cv2.imshow(WINDOW, frame)
        if cv2.waitKey(1) & 0xFF == 27:
            return None
    return min_r


def measure_hand_scale(cap, landmarker, duration=3.0):
    """双手张开静置, 测左手手部尺度中位数。"""
    scales = []
    t0 = time.time()
    while time.time() - t0 < duration:
        ok, frame = cap.read()
        if not ok:
            continue
        frame = cv2.flip(frame, 1)
        h, w = frame.shape[:2]
        roles = detect_roles(landmarker, frame)
        lm = roles.get("L") or roles.get("R")
        if lm is not None:
            a = px(lm, 0, w, h)
            b = px(lm, 9, w, h)
            scales.append(((a[0]-b[0])**2 + (a[1]-b[1])**2) ** 0.5)
            draw_skeleton(frame, lm)
        frame = draw_cn(frame, "步骤1/2: 双手张开静置", (16, 12),
                        size=28, color=(0, 255, 255))
        remaining = max(0.0, duration - (time.time() - t0))
        frame = draw_cn(frame, f"剩余 {remaining:.1f}s", (16, 48),
                        size=22, color=(0, 200, 255))
        cv2.imshow(WINDOW, frame)
        if cv2.waitKey(1) & 0xFF == 27:
            return None
    return statistics.median(scales) if scales else None


def main():
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("无法打开摄像头, 标定中止。")
        return
    landmarker = make_landmarker()
    try:
        # 步骤1: 测手部尺度
        scale = measure_hand_scale(cap, landmarker)
        if scale is None:
            print("未检测到手, 标定中止。")
            return

        # 步骤2: 逐个敲左手字母键 + 空格 + 退格
        targets = [("L", k["digit"], k["lm"]) for k in gc.LEFT_LETTERS]
        targets += [("L", "空格", gc.LEFT_SPACE["lm"]),
                    ("L", "退格", gc.LEFT_BACK["lm"])]
        min_ratios = []
        lm_ratios = {}   # lm -> min_ratio
        for hand, label, lm in targets:
            side = "左手" if hand == "L" else "右手"
            r = run_tap(cap, landmarker, f"步骤2/2: {side}敲 [{label}]", hand, lm)
            if r is None:
                print("用户中止。")
                return
            if r is not None:
                min_ratios.append(r)
                lm_ratios[lm] = r
                print(f"  {side} {label}: min_ratio={r:.3f}")

        # 基础阈值只用「容易的键」(REACH_FACTOR=1.0), 难键靠系数单独放大,
        # 否则最难够到的键会把全局阈值顶得过高, 导致乱触发。
        easy = [r for lm, r in lm_ratios.items() if gc.REACH_FACTOR.get(lm, 1.0) == 1.0]
        base_ratios = easy if easy else min_ratios
        threshold = gc.recommend_threshold(base_ratios)
        print(f"\n基础阈值依据(容易键): {[round(r,3) for r in base_ratios]}")
        print(f"推荐阈值: {threshold:.3f}")

        cfg = {"threshold": round(threshold, 3), "calibrated": True,
               "hand_scale": round(scale, 3)}
        ok = config_mod.save_config(cfg)
        print("已写入 config.json" if ok else "写 config.json 失败!")
    finally:
        landmarker.close()
        cap.release()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
