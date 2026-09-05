# -*- coding: utf-8 -*-
"""
gesture_core.py —— PalmT9 触发判定纯逻辑（双次捏合版）
======================================================
无摄像头依赖，供 sim.py 仿真和 palm_t9.py 复用。

核心模型：双次捏合（double-pinch）。
    一次有效按键 = 拇指尖快速捏合目标指腹两次：
        靠近(<close) → 松开(>release) → 再靠近(<close) → 松开(>release) → 触发
    静止不动不会产生任何按键，天然防误触。

键位布局：
    左手 12 键（拇指敲食指/中指/无名指/小指的指腹）：
        食指: 1(.,?!) 2(ABC) 3(DEF)
        中指: 4(GHI) 5(JKL) 6(MNO)
        无名指: 7(PQRS) 8(TUV) 9(WXYZ)
        小指: 删除  0  确认
    右手 10 键（数字 0-9）：
        食指: 1 2 3   中指: 4 5 6   无名指: 7 8 9   小指: 0(尖)
"""
import math
from collections import deque

# ---------------- 双次捏合参数（可调） ----------------
PINCH_CLOSE = 0.34      # 拇指尖到目标指腹距离比 < 此值 = 捏合
PINCH_RELEASE = 0.55    # > 此值 = 松开
MAX_INTERVAL = 0.5      # 两次捏合的最大间隔(秒)
MIN_INTERVAL = 0.06     # 两次捏合的最小间隔(秒, 防抖)
COOLDOWN = 0.18         # 触发后冷却(秒)
REACH_FACTOR = {14: 1.4, 15: 1.15, 18: 1.2, 19: 1.15, 20: 1.1}

# ---------------- 键位表 ----------------
# 左手 12 键：每根手指 指尖(TIP)/远端(DIP)/近端(PIP)
# kind: letter / func
LEFT_KEYS = [
    # 食指
    {"key": "1",  "label": "1.,?!", "lm": 8,  "kind": "letter"},
    {"key": "2",  "label": "2ABC",  "lm": 7,  "kind": "letter"},
    {"key": "3",  "label": "3DEF",  "lm": 6,  "kind": "letter"},
    # 中指
    {"key": "4",  "label": "4GHI",  "lm": 12, "kind": "letter"},
    {"key": "5",  "label": "5JKL",  "lm": 11, "kind": "letter"},
    {"key": "6",  "label": "6MNO",  "lm": 10, "kind": "letter"},
    # 无名指
    {"key": "7",  "label": "7PQRS", "lm": 16, "kind": "letter"},
    {"key": "8",  "label": "8TUV",  "lm": 15, "kind": "letter"},
    {"key": "9",  "label": "9WXYZ", "lm": 14, "kind": "letter"},
    # 小指功能键
    {"key": "BACK",  "label": "删", "lm": 20, "kind": "back"},     # 小指尖
    {"key": "0",     "label": "0",  "lm": 19, "kind": "digit"},    # 小指远端 = 数字0
    {"key": "ENTER", "label": "确认", "lm": 18, "kind": "enter"},   # 小指近端
]
# 右手 10 键 = 数字 0-9（食指123 中指456 无名指789 小指尖0）
RIGHT_KEYS = [
    {"key": "1", "lm": 8}, {"key": "2", "lm": 7}, {"key": "3", "lm": 6},
    {"key": "4", "lm": 12}, {"key": "5", "lm": 11}, {"key": "6", "lm": 10},
    {"key": "7", "lm": 16}, {"key": "8", "lm": 15}, {"key": "9", "lm": 14},
    {"key": "0", "lm": 20},
]

DIGIT_TO_LETTERS = {
    "1": ".,?!", "2": "ABC", "3": "DEF", "4": "GHI", "5": "JKL",
    "6": "MNO", "7": "PQRS", "8": "TUV", "9": "WXYZ",
}


def build_targets(role):
    if role == "L":
        return [(k["kind"], k["key"], k["lm"], k.get("label", k["key"]))
                for k in LEFT_KEYS]
    return [("digit", k["key"], k["lm"], k["key"]) for k in RIGHT_KEYS]


# ---------------- 英文 T9 词典 ----------------
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
    ("come", 0.24), ("did", 0.24), ("number", 0.23), ("sound", 0.23), ("now", 0.15),
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


def word_to_seq(word):
    return "".join(LETTER_TO_DIGIT.get(c, "") for c in word)


SEQ_MAP = {}
for _w, _f in WORD_FREQ:
    SEQ_MAP.setdefault(word_to_seq(_w), []).append((_w, _f))
for _s in SEQ_MAP:
    SEQ_MAP[_s].sort(key=lambda x: -x[1])


def candidates_for(digits):
    return SEQ_MAP.get("".join(digits), [])


# ---------------- 中文拼音 T9 -> 汉字 ----------------
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


# ---------------- 状态 ----------------
class GestureState:
    def __init__(self):
        self.threshold = 0.34
        # 双次捏合状态机（每只手独立）
        self._pinch = {}          # role -> {"stage","key","t_release","cooldown"}
        # 文本
        self.digits = []
        self.committed = ""
        self.sel_idx = 0
        self.shift = False
        self.cn_mode = False


def eff_threshold(state, lm):
    return state.threshold * REACH_FACTOR.get(lm, 1.0)


def candidates_for_mode(state, digits):
    return candidates_cn(digits) if state.cn_mode else candidates_for(digits)


def commit(state):
    if state.digits:
        cands = candidates_for_mode(state, state.digits)
        if cands:
            word = cands[state.sel_idx % len(cands)][0]
        else:
            word = "".join(state.digits)
        if (not state.cn_mode) and state.shift and word:
            word = word[0].upper() + word[1:]
        state.committed += word + " "
        state.digits.clear()
        state.sel_idx = 0
        state.shift = False
        return word
    state.committed += " "
    return " "


def cycle_candidate(state):
    n = len(candidates_for_mode(state, state.digits))
    state.sel_idx = (state.sel_idx + 1) % max(1, n)
    return state.sel_idx


def backspace(state):
    if state.digits:
        return state.digits.pop()
    if state.committed:
        ch = state.committed[-1]
        state.committed = state.committed[:-1]
        return ch
    return None


def _dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


# ---------------- 校正 ----------------
def estimate_hand_scale(lm):
    if not lm or len(lm) < 21:
        return None
    return _dist(lm[0], lm[9]) or None


def recommend_threshold(min_ratios, safety=1.4, lo=0.2, hi=0.7):
    if not min_ratios:
        return 0.34
    return max(lo, min(hi, max(min_ratios) * safety))


# ---------------- 遮挡补偿 ----------------
def _occlude_lm(lm, idx):
    """返回关键点坐标; 若被遮挡(None), 用相邻关节插值 + 上一帧兜底。"""
    if lm is None or idx >= len(lm):
        return None
    p = lm[idx]
    if p is not None:
        return p
    # 相邻关节插值(按指节相邻索引)
    neighbors = {8: (7, 7), 7: (8, 6), 6: (7, 5),      # 食指
                 12: (11, 11), 11: (12, 10), 10: (11, 9),  # 中指
                 16: (15, 15), 15: (16, 14), 14: (15, 13),  # 无名指
                 20: (19, 19), 19: (20, 18), 18: (19, 17)}  # 小指
    a_idx, b_idx = neighbors.get(idx, (idx - 1, idx + 1))
    a = lm[a_idx] if 0 <= a_idx < len(lm) else None
    b = lm[b_idx] if 0 <= b_idx < len(lm) else None
    if a and b:
        return ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
    return a or b


# ---------------- 核心：双次捏合状态机 ----------------
def evaluate_frame(hands, state, now):
    """对一帧双手关键点做判定，返回本帧触发的按键事件列表。

    每个事件: {"key": ..., "kind": ..., "role": "L"/"R", "label": ..., "ratio": float}

    一次有效按键 = 拇指尖对同一目标指腹快速捏两次：
        靠近(d/scale < close) → 松开(>release) → 再靠近 → 再松开 → 触发
    """
    events = []

    for role, lm in hands.items():
        if not lm or len(lm) < 21:
            continue
        thumb = lm[4]
        if thumb is None:
            continue
        scale = _dist(lm[0], lm[9]) or 1.0

        # 找该手拇指尖最近的目标键（按归一化距离比；目标点做遮挡补偿）
        best = None
        best_ratio = 1e9
        for kind, key, tlm, label in build_targets(role):
            p = _occlude_lm(lm, tlm)
            if p is None:
                continue
            d = _dist(thumb, p)
            ratio = d / scale
            if ratio < best_ratio:
                best_ratio = ratio
                best = (kind, key, tlm, label)

        st = state._pinch.setdefault(role, {
            "stage": "idle", "key": None, "t_release": 0.0, "cooldown": 0.0})

        if best is None:
            st["stage"] = "idle"
            st["key"] = None
            continue

        # 该键因难够程度放宽阈值
        factor = REACH_FACTOR.get(best[2], 1.0)
        close_th = PINCH_CLOSE * factor
        release_th = PINCH_RELEASE * factor
        key_id = (best[0], best[1], best[2])
        in_contact = best_ratio < close_th

        stage = st["stage"]
        if stage == "idle":
            if in_contact:
                st["stage"] = "first_closed"
                st["key"] = key_id
        elif stage == "first_closed":
            if key_id != st["key"]:
                st["stage"] = "idle"; st["key"] = None
            elif best_ratio >= release_th:
                st["stage"] = "released"
                st["t_release"] = now
        elif stage == "released":
            if key_id != st["key"]:
                st["stage"] = "idle"; st["key"] = None
            elif now - st["t_release"] > MAX_INTERVAL:
                st["stage"] = "idle"; st["key"] = None
            elif in_contact and (now - st["t_release"]) >= MIN_INTERVAL:
                st["stage"] = "second_closed"
        elif stage == "second_closed":
            if key_id != st["key"]:
                st["stage"] = "idle"; st["key"] = None
            elif best_ratio >= release_th and now >= st["cooldown"]:
                st["stage"] = "idle"
                st["key"] = None
                st["cooldown"] = now + COOLDOWN
                events.append({
                    "key": best[1], "kind": best[0], "role": role,
                    "label": best[3], "ratio": round(best_ratio, 3),
                })
    return events
