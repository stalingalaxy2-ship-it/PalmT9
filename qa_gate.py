# -*- coding: utf-8 -*-
"""qa_gate.py —— PalmT9 产品交付质量门禁（一键验收）

用法: python qa_gate.py
产出: qa_report.json / qa_report.md, 退出码 0=通过 1=不通过
门槛:
  - 单元/仿真测试全绿 (pytest test_product_qa.py + 既有 test_gesture_core.py test_calibration.py)
  - 交付文件齐全、模型文件有效
  - 核心模块可导入、无语法错误
视觉验收（需摄像头）请另行运行 acceptance.py，并把结果截图存档。
"""
import json
import subprocess
import sys
import time
import os

ROOT = os.path.dirname(os.path.abspath(__file__))
os.chdir(ROOT)

GATE = {
    "pytest_files": ["test_product_qa.py", "test_gesture_core.py", "test_calibration.py"],
    "deliverables": [
        "palm_t9.py", "gesture_core.py", "calibrate.py", "config.py",
        "launcher.py", "start.bat", "build_exe.bat", "requirements.txt",
        "README.md", "产品手册.md", "使用说明.md", "交付清单.md",
        "hand_landmarker.task",
    ],
}


def run_pytest():
    cmd = [sys.executable, "-m", "pytest", *GATE["pytest_files"], "-q", "--tb=line"]
    p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    tail = (p.stdout or "").strip().splitlines()
    summary = tail[-1] if tail else ""
    failed = [l for l in tail if l.startswith("FAILED")]
    return p.returncode == 0, summary, failed


def check_deliverables():
    missing, weak = [], []
    for f in GATE["deliverables"]:
        p = os.path.join(ROOT, f)
        if not os.path.isfile(p):
            missing.append(f)
        elif f == "hand_landmarker.task" and os.path.getsize(p) < 1_000_000:
            weak.append(f"{f} (模型文件异常小)")
        elif f.endswith(".py") and os.path.getsize(p) < 100:
            weak.append(f"{f} (内容疑似为空)")
    return missing, weak


def check_imports():
    bad = []
    for mod in ["gesture_core", "config", "logging_setup", "retry_utils"]:
        p = subprocess.run([sys.executable, "-c", f"import {mod}"],
                           capture_output=True, text=True)
        if p.returncode != 0:
            bad.append(f"{mod}: {(p.stderr or '').strip().splitlines()[-1] if p.stderr else 'unknown'}")
    return bad


def main():
    report = {"time": time.strftime("%Y-%m-%d %H:%M:%S"), "checks": {}}

    ok_py, summary, failed = run_pytest()
    report["checks"]["pytest"] = {"pass": ok_py, "summary": summary, "failed": failed}

    missing, weak = check_deliverables()
    report["checks"]["deliverables"] = {"pass": not missing and not weak,
                                        "missing": missing, "weak": weak}

    bad_imports = check_imports()
    report["checks"]["imports"] = {"pass": not bad_imports, "errors": bad_imports}

    overall = all(c["pass"] for c in report["checks"].values())
    report["overall_pass"] = overall

    with open("qa_report.json", "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    lines = [f"# PalmT9 交付质量门禁报告", f"- 时间: {report['time']}",
             f"- 总判定: **{'通过 PASS' if overall else '不通过 FAIL'}**", ""]
    lines.append(f"## 自动化测试: {'PASS' if ok_py else 'FAIL'}")
    lines.append(f"```\n{summary}\n```")
    for l in failed:
        lines.append(f"- {l}")
    lines.append(f"\n## 交付文件: {'PASS' if not missing and not weak else 'FAIL'}")
    for m in missing: lines.append(f"- 缺失: {m}")
    for w in weak: lines.append(f"- 异常: {w}")
    lines.append(f"\n## 模块导入: {'PASS' if not bad_imports else 'FAIL'}")
    for b in bad_imports: lines.append(f"- {b}")
    lines.append("\n## 待人工验收项（视觉/体验）")
    lines.append("- [ ] 摄像头实跑 acceptance.py，逐键视觉验收通过")
    lines.append("- [ ] launcher.py / start.bat 首次运行自动标定流程顺畅")
    lines.append("- [ ] build_exe.bat 打包产物在干净机器可运行")
    lines.append("- [ ] 演示场景: 盲打 hello / 你好 / 数字 全通过")

    with open("qa_report.md", "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print("\n".join(lines))
    sys.exit(0 if overall else 1)


if __name__ == "__main__":
    main()
