# -*- coding: utf-8 -*-
"""tests 包 —— 全部是离线测试，不需要模拟器/游戏/网络。

跑法（在项目根目录）：
    python -m unittest discover -s tests -t . -v

临时文件都放在项目下的 tmp_tests/ 里（已在 .gitignore 中），
刻意【不】用 tempfile.mkdtemp 建子目录，也不用系统 %TEMP%：
有些受限环境（CI 沙箱、安全软件）对「刚创建出来的目录」写入会直接拒绝，
而 cv2.imwrite 失败时只返回 False，不报错，很难查。
"""
import os
import shutil
import uuid

# 项目根目录（tests 的上一级）
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TMP_ROOT = os.path.join(PROJECT_ROOT, "tmp_tests")


def ensure_tmp_root():
    os.makedirs(TMP_ROOT, exist_ok=True)
    return TMP_ROOT


def unique_name(tag):
    """给测试文件起一个不会撞名的名字（只返回文件名，不建目录）。"""
    return f"t_{os.getpid()}_{uuid.uuid4().hex[:8]}_{tag}"


def cleanup():
    """清掉临时目录（测试结束时调用）。"""
    shutil.rmtree(TMP_ROOT, ignore_errors=True)
