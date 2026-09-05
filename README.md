# 掌上九键 PalmT9

让手掌成为 XR 时代随身携带的触觉键盘。

> Anchor · 具构（Origin AI Summit 深圳场 · Physical AI 赛道 A）参赛项目

## 一句话

当 XR 头显让键盘和触屏「消失」，我们用摄像头 + AI，把手掌本身变成一块摸得着、盲打得了的九键键盘。

## 运行前准备

1. 安装依赖（Python 3.11+）：

   ```powershell
   pip install -r requirements.txt
   ```

2. 模型文件 `hand_landmarker.task` 已在项目根目录（离线可用）。若无，下载：
   `https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task`

3. 一个 USB 摄像头 + 小音箱（可选，点击声）。

## 运行

```powershell
python palm_t9.py
```

## 键位（双手自敲）

| 手 | 手指 | 指尖 | 远端(第二节) | 近端(第三节) |
|---|---|---|---|---|
| 左手(字母) | 食指 | 1 .,?! | 4 GHI | 7 PQRS |
| 左手(字母) | 中指 | 2 ABC | 5 JKL | 8 TUV |
| 左手(字母) | 无名指 | 3 DEF | 6 MNO | 9 WXYZ |
| 右手(数字) | 食指 | 1 | 4 | 7 |
| 右手(数字) | 中指 | 2 | 5 | 8 |
| 右手(数字) | 无名指 | 3 | 6 | 9 |

- 左手小指：**尖 = 空格/确认**，远端 = **退格/删除**，近端 = **切换候选**
- 右手小指：**尖 = 数字 0**，远端 = **符号**（. , ! ? 循环），近端 = **大小写(Shift)**

**左手拇指敲左手键，右手拇指敲右手键。**

## 操作

| 键 | 作用 |
|---|---|
| `[` / `]` | 调小 / 调大触发阈值 |
| `h` | 交换左右手（键位标错手时） |
| `m` | 切换中英文输入 |
| `c` | 清空输入 |
| `ESC` | 退出 |

## 标定

```powershell
python calibrate.py      # 一键标定: 张手测尺度 + 逐键测阈值 -> 写入 config.json
python launcher.py       # 首次运行自动标定, 之后直接启动
# 或双击 start.bat
```

## 测试

```powershell
python sim.py                            # 无头仿真测试（不需要摄像头）
python acceptance.py                     # 视觉验收（需要摄像头）
python -m pytest test_gesture_core.py test_calibration.py -v   # 单元测试
```

## 目录

| 文件 | 作用 |
|---|---|
| `palm_t9.py` | 主程序（摄像头实时盲打） |
| `gesture_core.py` | 触发判定纯逻辑（无摄像头依赖） |
| `sim.py` | 无头仿真测试基座 |
| `acceptance.py` | 视觉验收工具 |
| `calibrate.py` | 一键标定 |
| `config.py` | 配置读写（config.json） |
| `launcher.py` / `start.bat` | 一键启动 |
| `logging_setup.py` | 日志（palm_t9.log） |
| `test_gesture_core.py` / `test_calibration.py` | 单元测试 |
| `build_exe.bat` | 打包成 exe（PyInstaller） |
| `hand_landmarker.task` | 手部关键点模型（离线） |
| `产品手册.md` / `交付清单.md` | 文档 |
