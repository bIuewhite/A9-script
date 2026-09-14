# -*- coding: utf-8 -*-
"""
adb_helper.py —— 雷电模拟器 ADB 操作封装
"""
import os
import re
import random
import subprocess
import time

import config

# Windows 下隐藏子进程的控制台窗口。
# 桌面版用 pythonw（无控制台）启动，若不隐藏，每次调用 adb.exe 都会弹出一个黑框。
_NO_WINDOW = 0x08000000 if os.name == "nt" else 0


class ADBError(Exception):
    pass


class ADB:
    def __init__(self, adb_path=None, serial=None):
        self.adb = adb_path or config.ADB_PATH
        self.serial = serial or config.DEVICE_SERIAL
        if not os.path.exists(self.adb):
            raise ADBError(f"找不到 adb.exe：{self.adb}")

    # ---------------- 底层 ----------------
    def _base(self):
        return [self.adb, "-s", self.serial]

    def _run(self, *args, timeout=30):
        """执行 adb 命令并返回 stdout 文本；失败抛 ADBError。"""
        try:
            p = subprocess.run(self._base() + list(args),
                               capture_output=True, timeout=timeout,
                               creationflags=_NO_WINDOW)
        except FileNotFoundError as e:
            raise ADBError(f"adb.exe 不存在: {self.adb}") from e
        except subprocess.TimeoutExpired as e:
            raise ADBError(f"adb 命令超时: {' '.join(args)}") from e
        if p.returncode != 0:
            err = (p.stderr or p.stdout).decode("utf-8", "ignore").strip()
            raise ADBError(f"adb 命令失败 [{p.returncode}] {' '.join(args)}: {err}")
        return p.stdout.decode("utf-8", "ignore")

    def _run_raw(self, *args, timeout=20):
        """执行 adb 命令，返回 (returncode, stdout_bytes)，不抛错。"""
        try:
            p = subprocess.run(self._base() + list(args),
                               capture_output=True, timeout=timeout,
                               creationflags=_NO_WINDOW)
            return p.returncode, p.stdout
        except (FileNotFoundError, subprocess.TimeoutExpired) as e:
            raise ADBError(f"adb 命令异常: {e}") from e

    # ---------------- 设备 ----------------
    def devices(self):
        p = subprocess.run([self.adb, "devices"], capture_output=True, timeout=15,
                           creationflags=_NO_WINDOW)
        return p.stdout.decode("utf-8", "ignore")

    def foreground_package(self):
        """返回当前前台应用包名；解析失败返回 None。"""
        out = self._run("shell", "dumpsys", "window")
        m = re.search(r"mCurrentFocus=Window\{[^}]*?\s([\w.$]+)/", out)
        if not m:
            m = re.search(r"mFocusedApp=.*?\s([\w.$]+)/", out)
        return m.group(1) if m else None

    # ---------------- 点击 / 滑动 ----------------
    def tap(self, x, y):
        self._run("shell", "input", "tap", str(int(x)), str(int(y)))

    def double_tap(self, x, y, gap_min_ms=None, gap_max_ms=None):
        """双击：在单条 shell 命令内 sleep 小数秒，保证两次点击间隔精确。"""
        gap_min = gap_min_ms if gap_min_ms is not None else config.NITRO_GAP_MIN_MS
        gap_max = gap_max_ms if gap_max_ms is not None else config.NITRO_GAP_MAX_MS
        gap_ms = random.randint(int(gap_min), int(gap_max))
        gap_s = gap_ms / 1000.0
        cmd = f"input tap {int(x)} {int(y)}; sleep {gap_s:.3f}; input tap {int(x)} {int(y)}"
        self._run("shell", cmd)

    def swipe(self, x1, y1, x2, y2, duration_ms=400):
        self._run("shell", "input", "swipe",
                  str(int(x1)), str(int(y1)), str(int(x2)), str(int(y2)),
                  str(int(duration_ms)))

    # ---------------- 截图 ----------------
    def screencap_bytes(self):
        """截取当前屏幕，返回 PNG 原始字节（不落盘）。"""
        rc, data = self._run_raw("exec-out", "screencap", "-p", timeout=20)
        if rc != 0 or not data:
            raise ADBError("截图失败 (exec-out screencap -p)")
        return data

    def screencap_file(self, save_path=None):
        """截取当前屏幕并保存到本地文件，返回路径。"""
        data = self.screencap_bytes()
        if save_path is None:
            os.makedirs(config.SHOT_DIR, exist_ok=True)
            save_path = os.path.join(
                config.SHOT_DIR,
                time.strftime("shot_%Y%m%d_%H%M%S_") + f"{int(time.time()*1000) % 1000:03d}.png",
            )
        os.makedirs(os.path.dirname(os.path.abspath(save_path)), exist_ok=True)
        with open(save_path, "wb") as f:
            f.write(data)
        return save_path

    # ---------------- 应用 ----------------
    def force_stop(self, pkg=None):
        self._run("shell", "am", "force-stop", pkg or config.GAME_PACKAGE)

    def start_app(self, activity=None):
        activity = activity or config.GAME_ACTIVITY
        self._run("shell", "am", "start", "-n", activity)
