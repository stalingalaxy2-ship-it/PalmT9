# -*- coding: utf-8 -*-
"""
logging_setup.py —— PalmT9 日志
================================
把运行日志写到 palm_t9.log(追加), 同时打印到控制台。
真机排错时, 用户把 palm_t9.log 发我即可定位。
"""
import logging
import os
import sys

LOG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "palm_t9.log")


def setup_logging():
    logger = logging.getLogger("palm_t9")
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")

    fh = logging.FileHandler(LOG_PATH, encoding="utf-8")
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    logger.addHandler(sh)
    return logger


def get_logger():
    return setup_logging()
