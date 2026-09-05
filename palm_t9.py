# -*- coding: utf-8 -*-
"""
掌上九键 PalmT9 —— MVP（极简贴骨 UI）
======================================
左手 = 字母九键(诺基亚式 T9), 右手 = 数字 0-9, 小指 = 空格/退格/符号。
键位只在关节上钉一个小圆点+一位数字(贴住骨骼); 拇指靠近某键时,
才浮现一个完整含义的提示框, 避免满屏大标签。

用法:
    python palm_t9.py          # 首次运行前确保同目录有 hand_landmarker.task

键位布局(每根手指=T9一列, 指节=行):
    左手(字母):  食指147  中指258  无名指369
    左手小指:    尖=空格/确认   远端=退格/删除
    右手(数字):  食指147  中指258  无名指369   小指尖=0
    右手小指远端: 符号(.,!? 循环)

操作:
    左手拇指敲左手字母键, 右手拇指敲右手数字键
    键盘  [ / ] 调阈值   h 交换左右手   c 清空   ESC 退出
"""
import math
import os
import time
from collections import deque

import cv2
import numpy as np
import mediapipe as mp
from mediapipe.tasks.python import vision
from mediapipe.tasks.python.core.base_options import BaseOptions
from PIL import Image, ImageDraw, ImageFont

import config as config_mod
from logging_setup import get_logger

log = get_logger()

MODEL_PATH = "hand_landmarker.task"

# ---------------- 点击声 ----------------
try:
    import winsound

    def click():
        winsound.Beep(880, 40)
except Exception:
    def click():
        print("\a", end="", flush=True)


# ---------------- 中文字体 ----------------
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
    _font_cache[size] = ImageFont.load_default()
    return _font_cache[size]


# ---------------- 键位表 ----------------
LEFT_LETTERS = [
    {"digit": "1", "lm": 8}, {"digit": "4", "lm": 7}, {"digit": "7", "lm": 6},
    {"digit": "2", "lm": 12}, {"digit": "5", "lm": 11}, {"digit": "8", "lm": 10},
    {"digit": "3", "lm": 16}, {"digit": "6", "lm": 15}, {"digit": "9", "lm": 14},
]
RIGHT_DIGITS = [
    {"digit": "1", "lm": 8}, {"digit": "4", "lm": 7}, {"digit": "7", "lm": 6},
    {"digit": "2", "lm": 12}, {"digit": "5", "lm": 11}, {"digit": "8", "lm": 10},
    {"digit": "3", "lm": 16}, {"digit": "6", "lm": 15}, {"digit": "9", "lm": 14},
]
LEFT_SPACE = {"lm": 20}   # 左小指尖 = 空格/确认
LEFT_BACK = {"lm": 19}    # 左小指远端 = 退格/删除
LEFT_CYCLE = {"lm": 18}   # 左小指近端 = 切换候选词
RIGHT_ZERO = {"lm": 20}   # 右小指尖 = 数字 0
RIGHT_SYM = {"lm": 19}    # 右小指远端 = 符号
RIGHT_SHIFT = {"lm": 18}  # 右小指近端 = 大小写切换

DIGIT_TO_LETTERS = {
    "1": ".,?!", "2": "ABC", "3": "DEF", "4": "GHI", "5": "JKL",
    "6": "MNO", "7": "PQRS", "8": "TUV", "9": "WXYZ",
}

REACH_FACTOR = {14: 1.5, 15: 1.15, 18: 1.2, 19: 1.2, 20: 1.1}
SYMBOLS = [".", ",", "!", "?", ";", ":", "@", "#", "&", "-"]
SPEED_MIN = 0.18   # 提高敲击速度门槛，过滤静止手的视觉抖动
SPEED_WINDOW = 4   # 速度滑窗帧数
DWELL_FRAMES = 2   # 同一键需连续接触>=此帧数才触发(防路过误触)

# 颜色 (OpenCV BGR)
C_LETTER = (60, 200, 60)     # 绿 字母
C_DIGIT = (255, 160, 40)     # 蓝 数字
C_SPACE = (0, 210, 210)      # 黄 空格
C_BACK = (0, 140, 255)       # 橙 退格
C_SYM = (220, 90, 200)       # 紫 符号
C_CYCLE = (200, 200, 200)    # 白灰 切换候选
C_SHIFT = (180, 180, 255)    # 浅蓝 大小写
COLOR_BY_KIND = {"letter": C_LETTER, "digit": C_DIGIT,
                 "space": C_SPACE, "back": C_BACK, "symbol": C_SYM,
                 "cycle": C_CYCLE, "shift": C_SHIFT}
FUNC_CHAR = {"space": "空", "back": "退", "symbol": "符", "cycle": "换",
             "shift": "Aa"}


# ---------------- T9 词典 ----------------
LETTER_TO_DIGIT = {
    "a": "2", "b": "2", "c": "2", "d": "3", "e": "3", "f": "3",
    "g": "4", "h": "4", "i": "4", "j": "5", "k": "5", "l": "5",
    "m": "6", "n": "6", "o": "6", "p": "7", "q": "7", "r": "7", "s": "7",
    "t": "8", "u": "8", "v": "8", "w": "9", "x": "9", "y": "9", "z": "9",
}

WORD_FREQ = [
    ("the", 1.00), ("to", 0.95), ("and", 0.90), ("a", 0.88), ("of", 0.85),
    ("hello", 0.80), ("home", 0.78), ("world", 0.75), ("good", 0.72),
    ("am", 0.71), ("hi", 0.70), ("going", 0.70), ("go", 0.68), ("in", 0.65),
    ("is", 0.65), ("it", 0.64), ("ok", 0.62), ("yes", 0.58), ("no", 0.58),
    ("my", 0.57), ("palm", 0.56), ("type", 0.55), ("key", 0.54),
    ("you", 0.63), ("that", 0.62), ("he", 0.60), ("was", 0.60), ("for", 0.58),
    ("on", 0.57), ("are", 0.57), ("with", 0.56), ("as", 0.55), ("i", 0.55),
    ("his", 0.54), ("they", 0.54), ("be", 0.53), ("at", 0.53), ("one", 0.52),
    ("have", 0.52), ("this", 0.51), ("from", 0.51), ("or", 0.50), ("had", 0.50),
    ("by", 0.49), ("hot", 0.49), ("word", 0.48), ("but", 0.48), ("what", 0.47),
    ("some", 0.47), ("we", 0.46), ("can", 0.46), ("out", 0.45), ("other", 0.45),
    ("were", 0.44), ("all", 0.44), ("there", 0.43), ("when", 0.43), ("up", 0.42),
    ("use", 0.42), ("your", 0.41), ("how", 0.41), ("said", 0.40), ("an", 0.40),
    ("each", 0.39), ("she", 0.39), ("which", 0.38), ("do", 0.38), ("their", 0.37),
    ("time", 0.37), ("if", 0.36), ("will", 0.36), ("way", 0.35), ("about", 0.35),
    ("many", 0.34), ("then", 0.34), ("them", 0.33), ("write", 0.33), ("would", 0.32),
    ("like", 0.32), ("so", 0.31), ("these", 0.31), ("her", 0.30), ("long", 0.30),
    ("make", 0.29), ("thing", 0.29), ("see", 0.28), ("him", 0.28), ("two", 0.27),
    ("has", 0.27), ("look", 0.26), ("more", 0.26), ("day", 0.25), ("could", 0.25),
    ("come", 0.24), ("did", 0.24), ("number", 0.23), ("sound", 0.23), ("no", 0.22),
    ("most", 0.22), ("people", 0.21), ("my", 0.21), ("over", 0.20), ("know", 0.20),
    ("water", 0.19), ("than", 0.19), ("call", 0.18), ("first", 0.18), ("who", 0.17),
    ("may", 0.17), ("down", 0.16), ("side", 0.16), ("been", 0.15), ("now", 0.15),
    ("find", 0.14), ("any", 0.14), ("new", 0.13), ("work", 0.13), ("part", 0.12),
    ("take", 0.12), ("get", 0.11), ("place", 0.11), ("made", 0.10), ("live", 0.10),
    ("where", 0.09), ("after", 0.09), ("back", 0.08), ("little", 0.08), ("only", 0.07),
    ("round", 0.07), ("man", 0.06), ("year", 0.06), ("came", 0.05), ("show", 0.05),
    ("every", 0.04), ("me", 0.04), ("give", 0.04), ("our", 0.03), ("under", 0.03),
    ("name", 0.03), ("very", 0.02), ("through", 0.02), ("just", 0.02), ("form", 0.02),
    ("great", 0.02), ("think", 0.01), ("say", 0.01), ("help", 0.01), ("low", 0.01),
    ("hand", 0.01), ("here", 0.01), ("read", 0.01), ("well", 0.01), ("also", 0.01),
    ("play", 0.01), ("small", 0.01), ("end", 0.01), ("put", 0.01), ("big", 0.01),
]


def word_to_seq(word: str) -> str:
    return "".join(LETTER_TO_DIGIT.get(c, "") for c in word)


SEQ_MAP = {}
for w, f in WORD_FREQ:
    SEQ_MAP.setdefault(word_to_seq(w), []).append((w, f))
for seq in SEQ_MAP:
    SEQ_MAP[seq].sort(key=lambda x: -x[1])


# ---------------- 状态 ----------------
class State:
    def __init__(self):
        self.digits = []
        self.committed = ""
        self.threshold = 0.34
        self.armed = True
        self.cooldown_until = 0.0
        self.swap = False
        self.last_action = "—"
        self.last_action_time = 0.0
        self.sym_idx = 0
        self.sel_idx = 0              # 当前选中候选词下标
        self.shift = False            # 一次性大写
        self.cn_mode = False          # 中文模式
        self.flash_px = None
        self.flash_until = 0.0
        self.thumb_hist = {}          # role -> deque((x,y)) 拇指尖轨迹
        self.dwell_key = None
        self.dwell_count = 0
        self.dwell_speed = 0.0        # 进入接触瞬间锁存的拇指真实速度


def candidates_for(digits):
    return SEQ_MAP.get("".join(digits), [])


# 中文拼音 T9 -> 汉字(离线小词典, 与 gesture_core 同步)
PY_WORDS = [
    ("nihao", "你好", 1.00), ("shijie", "世界", 0.95),
    ("xiexie", "谢谢", 0.80), ("zhongguo", "中国", 0.70),
    ("shuru", "输入", 0.65), ("zhangshang", "掌上", 0.60),
    ("jiujian", "九键", 0.55), ("mangda", "盲打", 0.50),
    ("jianpan", "键盘", 0.45), ("haode", "好的", 0.40),
    ("nihaoma", "你好吗", 0.35), ("woai", "我爱", 0.30),
    ("nizai", "你在", 0.28), ("ganma", "干嘛", 0.25),
]


def pinyin_to_seq(pinyin):
    return "".join(LETTER_TO_DIGIT.get(c, "") for c in pinyin)


PY_SEQ_MAP = {}
for _py, _hz, _f in PY_WORDS:
    PY_SEQ_MAP.setdefault(pinyin_to_seq(_py), []).append((_hz, _f))
for _s in PY_SEQ_MAP:
    PY_SEQ_MAP[_s].sort(key=lambda x: -x[1])


def candidates_cn(digits):
    return PY_SEQ_MAP.get("".join(digits), [])


def candidates_for_mode(state, digits):
    return candidates_cn(digits) if state.cn_mode else candidates_for(digits)


def set_action(state, text):
    state.last_action = text
    state.last_action_time = time.time()


def commit(state):
    if state.digits:
        cands = candidates_for_mode(state, state.digits)
        if cands:
            i = state.sel_idx % len(cands)
            word = cands[i][0]
        else:
            word = "".join(state.digits)
        if (not state.cn_mode) and state.shift and word:
            word = word[0].upper() + word[1:]
        state.committed += word + " "
        state.digits.clear()
        state.sel_idx = 0
        state.shift = False
        set_action(state, f"确认 ✓ {word}")
    else:
        state.committed += " "
        set_action(state, "空格")


def cycle_candidate(state):
    n = len(candidates_for_mode(state, state.digits))
    state.sel_idx = (state.sel_idx + 1) % max(1, n)
    set_action(state, f"候选 {state.sel_idx + 1}")
    return state.sel_idx


def backspace(state):
    if state.digits:
        d = state.digits.pop()
        set_action(state, f"删除 ✕ 键{d}")
    elif state.committed:
        ch = state.committed[-1]
        state.committed = state.committed[:-1]
        set_action(state, f"删除 ✕ '{ch}'")
    else:
        set_action(state, "删除 ✕ (空)")


def eff_threshold(state, lm):
    return state.threshold * REACH_FACTOR.get(lm, 1.0)


# ---------------- PIL 小贴图(带缓存, 不全屏转换) ----------------
_patch_cache = {}


def make_text_patch(text, font_size, bgr):
    key = (text, font_size, bgr)
    if key in _patch_cache:
        return _patch_cache[key]
    font = _get_font(font_size)
    tmp = Image.new("RGBA", (4, 4))
    tw = ImageDraw.Draw(tmp).textlength(text, font=font)
    pad = 8
    W = int(tw + pad * 2)
    H = int(font_size + pad * 2)
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    rgb = (bgr[2], bgr[1], bgr[0])  # BGR -> RGB
    d.rounded_rectangle([0, 0, W - 1, H - 1], radius=8,
                        fill=rgb + (225,), outline=(255, 255, 255, 255), width=1)
    d.text((pad, pad - 2), text, font=font, fill=(255, 255, 255, 255))
    patch = np.array(img)
    _patch_cache[key] = patch
    return patch


def paste_rgba(frame, patch, x, y):
    ph, pw = patch.shape[:2]
    H, W = frame.shape[:2]
    x0, y0 = max(0, x), max(0, y)
    x1, y1 = min(W, x + pw), min(H, y + ph)
    if x1 <= x0 or y1 <= y0:
        return
    sx0, sy0 = x0 - x, y0 - y
    sx1, sy1 = sx0 + (x1 - x0), sy0 + (y1 - y0)
    roi = frame[y0:y1, x0:x1].astype(np.float32)
    alpha = patch[sy0:sy1, sx0:sx1, 3:4].astype(np.float32) / 255.0
    rgb = patch[sy0:sy1, sx0:sx1, :3].astype(np.float32)
    bgr = rgb[:, :, ::-1]  # RGB -> BGR
    frame[y0:y1, x0:x1] = (bgr * alpha + roi * (1 - alpha)).astype(np.uint8)


# ---------------- 底部小面板 ----------------
def render_panel(state, width, hand_status):
    H = 128
    img = Image.new("RGB", (width, H), (18, 18, 24))
    d = ImageDraw.Draw(img)
    f_big = _get_font(32)
    f_mid = _get_font(20)
    f_sm = _get_font(16)

    d.rounded_rectangle([10, 6, width - 10, 60], radius=9,
                        outline=(0, 200, 90), width=2, fill=(26, 28, 34))
    committed = state.committed
    composing = "".join(state.digits)
    x = 20
    d.text((x, 16), committed, font=f_big, fill=(255, 255, 255))
    x += d.textlength(committed, font=f_big)
    if composing:
        d.text((x, 16), composing, font=f_big, fill=(0, 230, 230))
        x += d.textlength(composing, font=f_big)
    cursor = "_" if int(time.time() * 2) % 2 == 0 else " "
    d.text((x + 2, 16), cursor, font=f_big, fill=(0, 255, 120))

    cands = candidates_for_mode(state, state.digits)
    xx = 20
    for i, (wd, _) in enumerate(cands[:3]):
        # 高亮当前选中的候选词(sel_idx), 否则按位置给默认底色
        if i == state.sel_idx % max(1, len(cands)):
            bg, ol = (0, 130, 70), (0, 255, 140)
        else:
            bg, ol = (46, 48, 58), (0, 230, 130)
        d.rounded_rectangle([xx, 68, xx + 108, 96], radius=7,
                            fill=bg, outline=ol, width=2 if i == state.sel_idx % max(1, len(cands)) else 1)
        d.text((xx + 7, 71), f"{i+1}.{wd}", font=f_mid, fill=(255, 255, 255))
        xx += 118
    if not cands:
        d.text((xx, 71), "左手敲字母出候选", font=f_mid, fill=(110, 110, 110))

    age = time.time() - state.last_action_time
    act_color = (0, 255, 140) if age < 1.0 else (150, 150, 150)
    d.text((20, 102), f"最近:{state.last_action}", font=f_mid, fill=act_color)
    d.text((width - 350, 104),
           f"{hand_status}  阈值{state.threshold:.2f} [ ] h换手 c清空 ESC",
           font=f_sm, fill=(255, 210, 90))
    return cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)


def draw_joint_label(frame, p, text, color):
    """在关节点钉一个小圆点+紧贴的短文本(贴住骨骼)"""
    cv2.circle(frame, p, 8, color, -1)
    cv2.circle(frame, p, 8, (255, 255, 255), 1)
    cv2.putText(frame, text, (p[0] + 10, p[1] + 5),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 3, cv2.LINE_AA)
    cv2.putText(frame, text, (p[0] + 10, p[1] + 5),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1, cv2.LINE_AA)


# ---------------- 主程序 ----------------
def main():
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        log.error("无法打开摄像头(0)。请确认摄像头已连接/未被占用。")
        return

    options = vision.HandLandmarkerOptions(
        base_options=BaseOptions(model_asset_path=MODEL_PATH),
        running_mode=vision.RunningMode.VIDEO,
        num_hands=2,
        min_hand_detection_confidence=0.6,
        min_hand_presence_confidence=0.5,
        min_tracking_confidence=0.5,
    )
    landmarker = vision.HandLandmarker.create_from_options(options)

    state = State()
    # 加载标定配置(阈值), 免手动调参
    cfg = config_mod.load_config()
    state.threshold = float(cfg.get("threshold", 0.34))
    log.info("PalmT9 启动, threshold=%.3f calibrated=%s",
             state.threshold, cfg.get("calibrated", False))
    draw_utils = vision.drawing_utils
    connections = vision.HandLandmarksConnections.HAND_CONNECTIONS
    PANEL_H = 128

    # 预生成关节上的中文小贴图(空/退/符)
    FUNC_PATCH = {k: make_text_patch(v, 18, COLOR_BY_KIND[k])
                  for k, v in FUNC_CHAR.items()}

    print(__doc__)
    frame_idx = 0

    while True:
        ok, frame = cap.read()
        if not ok:
            break
        frame = cv2.flip(frame, 1)
        h, w = frame.shape[:2]

        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        timestamp_ms = frame_idx * 33
        frame_idx += 1
        result = landmarker.detect_for_video(mp_image, timestamp_ms)

        now = time.time()
        best = None
        best_score = 1e9
        best_thumb = None
        best_role = None
        joints = []   # (kind, payload, tlm, pos)
        speed_by_role = {}

        roles = {}
        if result.hand_landmarks:
            detected = []
            for i, lm in enumerate(result.hand_landmarks):
                detected.append((lm[0].x * w, lm))
                draw_utils.draw_landmarks(frame, lm, connections)
            detected.sort(key=lambda t: t[0])
            if len(detected) >= 2:
                roles["L"], roles["R"] = detected[0][1], detected[1][1]
            elif len(detected) == 1:
                wx, lm = detected[0]
                roles["L" if wx < w / 2 else "R"] = lm
            if state.swap and "L" in roles and "R" in roles:
                roles["L"], roles["R"] = roles["R"], roles["L"]

        for role, lm in roles.items():
            def px(j):
                return (int(lm[j].x * w), int(lm[j].y * h))

            thumb = px(4)
            wrist = px(0)
            mcp_mid = px(9)
            scale = math.hypot(wrist[0] - mcp_mid[0], wrist[1] - mcp_mid[1]) or 1.0

            # 拇指尖真实位移速度(占手部尺度/帧)
            hist = state.thumb_hist.setdefault(role, deque(maxlen=SPEED_WINDOW))
            hist.append(thumb)
            if len(hist) >= 2:
                first, last = hist[0], hist[-1]
                speed = (math.hypot(last[0] - first[0], last[1] - first[1]) / (len(hist) - 1)) / scale
            else:
                speed = 0.0
            speed_by_role[role] = speed

            if role == "L":
                targets = ([("letter", k["digit"], k["lm"]) for k in LEFT_LETTERS]
                           + [("space", None, LEFT_SPACE["lm"]),
                              ("back", None, LEFT_BACK["lm"]),
                              ("cycle", None, LEFT_CYCLE["lm"])])
            else:
                targets = ([("digit", k["digit"], k["lm"]) for k in RIGHT_DIGITS]
                           + [("digit", "0", RIGHT_ZERO["lm"]),
                              ("symbol", None, RIGHT_SYM["lm"]),
                              ("shift", None, RIGHT_SHIFT["lm"])])

            for kind, payload, tlm in targets:
                p = px(tlm)
                d = math.hypot(thumb[0] - p[0], thumb[1] - p[1])
                ratio = d / scale
                eff = eff_threshold(state, tlm)
                score = ratio / eff
                if score < best_score:
                    best_score = score
                    best = (kind, payload, p, tlm)
                    best_thumb = thumb
                    best_role = role
                joints.append((kind, payload, tlm, p))

        # ---------- 贴骨小标签(简洁: 圆点+短文本) ----------
        for kind, payload, tlm, p in joints:
            color = COLOR_BY_KIND[kind]
            if kind in ("letter", "digit"):
                draw_joint_label(frame, p, payload, color)
            else:
                # 功能键: 圆点 + 中文小贴图(空/退/符)
                cv2.circle(frame, p, 8, color, -1)
                cv2.circle(frame, p, 8, (255, 255, 255), 1)
                paste_rgba(frame, FUNC_PATCH[kind], p[0] + 10, p[1] - 10)

        # ---------- 触发判定(驻留 + 拇指真实速度) ----------
        key_id = (best[0], best[1], best[3]) if best else None
        if best is not None and best_score < 1.0:
            if key_id == state.dwell_key:
                state.dwell_count += 1
            else:
                state.dwell_key = key_id
                state.dwell_count = 1
                state.dwell_speed = speed_by_role.get(best_role, 0.0)
        else:
            state.dwell_key = None
            state.dwell_count = 0
            state.dwell_speed = 0.0

        if best and best_score < 1.0 \
                and state.dwell_speed >= SPEED_MIN \
                and state.dwell_count >= DWELL_FRAMES:
            if state.armed and now >= state.cooldown_until:
                state.armed = False
                state.cooldown_until = now + 0.35
                kind, payload, p, tlm = best
                if kind == "letter":
                    state.digits.append(payload)
                    state.sel_idx = 0
                    set_action(state, f"字母键 {payload}")
                elif kind == "digit":
                    state.committed += payload
                    set_action(state, f"数字 {payload}")
                elif kind == "space":
                    commit(state)
                elif kind == "back":
                    backspace(state)
                    state.sel_idx = 0
                elif kind == "cycle":
                    cycle_candidate(state)
                elif kind == "shift":
                    state.shift = not state.shift
                    set_action(state, "大写开" if state.shift else "大写关")
                elif kind == "symbol":
                    sym = SYMBOLS[state.sym_idx % len(SYMBOLS)]
                    state.committed += sym
                    state.sym_idx += 1
                    set_action(state, f"符号 '{sym}'")
                click()
                state.flash_px = p
                state.flash_until = now + 0.35
        else:
            if best_score > 1.5:
                state.armed = True

        # ---------- 唯一的悬停提示框(拇指靠近才浮现) ----------
        if best and best_score < 1.8:
            kind, payload, p, tlm = best
            color = COLOR_BY_KIND[kind]
            cv2.circle(frame, p, 16, (0, 255, 255), 2)
            if best_thumb:
                cv2.line(frame, best_thumb, p, (0, 255, 255), 1)
            if kind == "letter":
                tip = f"{payload} {DIGIT_TO_LETTERS[payload]}"
            elif kind == "digit":
                tip = payload
            elif kind == "space":
                tip = "空格/确认"
            elif kind == "back":
                tip = "退格/删除"
            elif kind == "cycle":
                tip = "切换候选"
            elif kind == "shift":
                tip = "大小写"
            else:
                tip = "符号"
            tpatch = make_text_patch(tip, 26, color)
            tph, tpw = tpatch.shape[:2]
            tx = p[0] - tpw - 14
            ty = p[1] - tph - 14
            if tx < 4:
                tx = p[0] + 14
            if ty < 4:
                ty = p[1] + 14
            cv2.line(frame, p, (tx + tpw // 2, ty + tph), (0, 255, 255), 1)
            paste_rgba(frame, tpatch, tx, ty)

        # 拇指标记
        if best_thumb:
            cv2.circle(frame, best_thumb, 8, (255, 255, 255), 2)

        # 命中闪光
        if state.flash_px and now < state.flash_until:
            cv2.circle(frame, state.flash_px, 24, (0, 0, 255), 3)

        # ---------- 底部面板 ----------
        hand_status = f"左手{'OK' if 'L' in roles else '--'} 右手{'OK' if 'R' in roles else '--'}"
        panel = render_panel(state, w, hand_status)
        frame[h - PANEL_H:h, 0:w] = panel

        cv2.imshow("PalmT9 (极简贴骨)", frame)
        key = cv2.waitKey(1) & 0xFF
        if key == 27:
            break
        elif key == ord("["):
            state.threshold = max(0.15, state.threshold - 0.02)
        elif key == ord("]"):
            state.threshold = min(0.90, state.threshold + 0.02)
        elif key == ord("c"):
            state.digits.clear()
            state.committed = ""
            state.sel_idx = 0
            state.shift = False
            set_action(state, "清空")
        elif key == ord("h"):
            state.swap = not state.swap
            set_action(state, f"交换左右手 swap={state.swap}")
        elif key == ord("m"):
            state.cn_mode = not state.cn_mode
            state.digits.clear()
            state.sel_idx = 0
            set_action(state, "中文模式" if state.cn_mode else "英文模式")

    landmarker.close()
    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        log.exception("PalmT9 运行崩溃")
        print("发生错误, 详情见 palm_t9.log")
        import traceback
        traceback.print_exc()
