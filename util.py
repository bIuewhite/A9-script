# -*- coding: utf-8 -*-
"""util.py —— 小工具（日志、目录）"""
import collections
import os
import threading
import time

import config

_log_lock = threading.Lock()
_log_deque = collections.deque(maxlen=3000)
_log_counter = 0

# 日志同时写文件，方便出问题时排查（之前的日志只存在内存里，一关就没了）
LOG_DIR = os.path.join(config.BASE_DIR, "logs")
LOG_FILE = os.path.join(LOG_DIR, "run.log")
_MAX_LOG_BYTES = 2 * 1024 * 1024


def _write_file(line):
    try:
        if not os.path.isdir(LOG_DIR):
            os.makedirs(LOG_DIR, exist_ok=True)
        if os.path.exists(LOG_FILE) and os.path.getsize(LOG_FILE) > _MAX_LOG_BYTES:
            try:
                os.replace(LOG_FILE, LOG_FILE + ".1")
            except Exception:
                pass
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def log(msg, *args):
    global _log_counter
    ts = time.strftime("%H:%M:%S")
    try:
        text = msg % args if args else msg
    except Exception:
        text = msg + " " + " ".join(str(a) for a in args)
    line = f"[{ts}] {text}"
    with _log_lock:
        _log_deque.append((_log_counter, line))
        _log_counter += 1
    print(line, flush=True)
    _write_file(line)


def get_logs_since(idx):
    """返回 (新增日志列表, 最新索引)。供界面增量拉取。"""
    with _log_lock:
        items = [t for i, t in _log_deque if i >= idx]
        latest = _log_counter
    return items, latest


def ensure_dirs():
    os.makedirs(config.TEMPLATE_DIR, exist_ok=True)
    os.makedirs(config.SHOT_DIR, exist_ok=True)
    os.makedirs(LOG_DIR, exist_ok=True)
