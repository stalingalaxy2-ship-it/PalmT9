# -*- coding: utf-8 -*-
"""
launcher.py —— PalmT9 一键启动入口
====================================
首次运行(无标定) -> 自动进入 calibrate.py 标定
已标定           -> 直接启动 palm_t9.py
"""
import sys


def main():
    import config as config_mod
    cfg = config_mod.load_config()
    if not cfg.get("calibrated"):
        print("检测到尚未标定, 首次运行将进入标定流程...")
        import calibrate
        calibrate.main()
        cfg = config_mod.load_config()
        if not cfg.get("calibrated"):
            print("标定未完成, 已退出。")
            return
    import palm_t9
    palm_t9.main()


if __name__ == "__main__":
    sys.exit(main())
