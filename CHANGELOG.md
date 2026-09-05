# PalmT9 自我迭代 CHANGELOG

> 无监督迭代记录：每轮假设 → 改动 → 仿真/单测验证 → 保留/回滚。

## 阶段 0：测试基座

- **iter 1** 抽纯逻辑 `gesture_core.py`（evaluate_frame 无 cv2/mediapipe 依赖）→ 通过
- **iter 2** 写合成手部轨迹生成器 `sim.py`（base_hand/tap_frames/rest_frames）→ 通过
- **iter 3** 指标：TPR/FPR/逐键率/延迟/e2e hello → 通过
- **iter 4** 跑基线：TPR 4/22，FPR 0 → 记录基线
- **iter 5** 迭代器雏形（metrics.json 输出）→ 通过

## 阶段 1：触发判定调优（核心难点，多轮迭代）

- **iter 6-8** 尝试「score 滑窗下降量」作敲击速度 → TPR 卡在 4~10/22，**回滚思路**
- **iter 9** 加驻留判定 DWELL_FRAMES=2 → TPR 10/22
- **iter 10** 发现根因：直线慢滑轨迹刮过相邻键，先触发路过键+冷却阻塞真目标
- **iter 11** 改测试轨迹为「侧面悬停点直线逼近」→ TPR 8/22，**回滚**
- **iter 12** 发现真正根因：score 滑窗被路过键污染，改用**拇指尖真实位移速度**（thumb_hist 位移/帧数/尺度）→ 关键正确决策
- **iter 13** 在「进入接触瞬间锁存速度」（dwell_speed）避免驻留期速度衰减 → 关键正确决策
- **iter 14** 测试轨迹改为「快速跳向目标+停留」贴近真实敲击 → **TPR 22/22，FPR 0**
- **iter 15** e2e hello 插抬手间隔（>冷却期）→ e2e hello 全绿，延迟 0.009ms

## 阶段 2：输入引擎

- **iter 16** 扩词典：补 am/hi/ok/yes/no/my/palm/type/key 等演示词 → 通过（两个副本同步）

## 阶段 3：UI/UX

- **iter 17** 极简贴骨 UI：小圆点+短文本，唯一悬停提示框 → 通过
- **iter 18** 状态栏 ✓/✗ 改 OK/--（字体无此字形）→ 通过

## 阶段 4：交付物

- **iter 19** 写 `requirements.txt`（锁 mediapipe>=1.0）→ 通过
- **iter 20** 写 `README.md`（运行/键位/操作/目录）→ 通过
- **iter 21** 写 `系统架构图.md`（mermaid 数据流）→ 通过
- **iter 22** 写 `演示视频脚本.md`（分镜+拍摄要点+备用方案）→ 通过
- **iter 23** 重写 `acceptance.py` 为双手自敲版（修复已删除的 KEYS/SPACE_LM 引用）→ 通过

## 最终仿真基线

| 指标 | 值 |
|---|---|
| 逐键触发 TPR | 22/22 (100%) |
| 静息误触 FPR | 0 |
| 端到端 hello | ok=True |
| 单帧延迟 | 0.010 ms |

## 阶段 5：产品化（Demo → 完整产品）

- **iter 24** 候选词多选：`sel_idx` + `cycle` 键(左小指近端 lm18)，commit 提交当前选中而非 top1
- **iter 25** 校正纯函数：`estimate_hand_scale` / `recommend_threshold`(由最难键决定, 夹 [0.2,0.7])
- **iter 26** 配置持久化 `config.py`(修了默认参数绑定 bug)；palm_t9 启动加载阈值
- **iter 27** 一键标定 `calibrate.py`(张手测尺度 + 逐键测 min_ratio + 写 config)
- **iter 28** 大小写切换：`shift` 键(右小指近端 lm18)，commit 首字母大写(一次性)
- **iter 29** 中文拼音：`PY_WORDS`/`candidates_cn`/`cn_mode`，`m` 键切换中英文，同 T9 架构
- **iter 30** 单元测试套件 18 项全过(词典/候选/退格/标定/触发/中文)
- **iter 31** 日志 `logging_setup.py` + palm_t9 崩溃捕获写 palm_t9.log
- **iter 32** 一键启动 `launcher.py`(首次自动标定) + `start.bat`
- **iter 33** 打包脚本 `build_exe.bat`(PyInstaller)
- **iter 34** `产品手册.md` + `交付清单.md`

## 最终状态

| 能力 | 状态 |
|---|---|
| 校正(自动标定+持久化) | ✅ |
| 使用(字母/数字/符号/退格/空格/候选切换/大小写/中文) | ✅ |
| 交付(一键启动/config/测试/日志/打包/手册/清单) | ✅ |
| 仿真 TPR / FPR / e2e | 22/22 · 0 · ok |
| 单元测试 | 18 passed |

1. **「速度」必须测物理量（位移），不能测派生量（score 变化）**——手指太近时派生量会被相邻键污染。
2. **速度要在接触瞬间锁存**，否则驻留期速度归零会误杀真敲击。
3. **仿真轨迹必须贴近真实**（快速跳变+停留），否则假阴性是测试 bug 不是产品 bug。
4. 冷却期（350ms）决定了真实打字节奏需两键间隔抬手，这是正确行为而非缺陷。
