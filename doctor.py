# -*- coding: utf-8 -*-
"""doctor.py —— 环境体检

把「为什么跑不起来」一次性说清楚：Python、依赖、adb、模拟器、分辨率、
游戏、模板，逐项检查并给出下一步该干什么。

· main.py check 用它
· setup_env.py（一键配置）也用它

只做检查和提示，不擅自改动系统。
"""
import os
import shutil
import subprocess
import sys

import config

MARK_OK = "[√]"
MARK_WARN = "[!]"
MARK_BAD = "[×]"

MIN_PYTHON = (3, 10)

# 常见雷电模拟器安装位置（用来在 adb 找不到时给提示）
LDPLAYER_SUBDIRS = (
    r"leidian\LDPlayer14\dnplayer.exe",
    r"leidian\LDPlayer9\dnplayer.exe",
    r"雷电模拟器\leidian\LDPlayer14\dnplayer.exe",
    r"LDPlayer\LDPlayer14\dnplayer.exe",
    r"LDPlayer\LDPlayer9\dnplayer.exe",
)


# ==================== 纯函数（好测） ====================
def version_tuple(text):
    """把 "3.14" 这种字符串转成 (3, 14)；解析不出来返回 ()。"""
    out = []
    for part in str(text).split("."):
        num = ""
        for ch in part:
            if ch.isdigit():
                num += ch
            else:
                break
        if num == "":
            break
        out.append(int(num))
    return tuple(out)


def parse_wm_size(text):
    """从 `wm size` 的输出里取分辨率。

    形如 "Physical size: 1920x1080"，也可能有 "Override size: ..."；
    优先取 Override（那是实际生效的）。取不到返回 None。
    """
    if not text:
        return None
    found = None
    for line in str(text).splitlines():
        low = line.lower()
        if "x" not in low:
            continue
        for token in line.replace(":", " ").split():
            if "x" in token:
                a, _, b = token.partition("x")
                if a.strip().isdigit() and b.strip().isdigit():
                    size = (int(a), int(b))
                    if "override" in low:
                        return size          # 实际生效的优先
                    found = found or size
    return found


def check_python(info=None):
    """检查 Python 版本。返回 (是否通过, 说明)。"""
    info = info or sys.version_info
    got = (info[0], info[1])
    if got >= MIN_PYTHON:
        return True, f"Python {info[0]}.{info[1]}.{info[2]}（需要 {MIN_PYTHON[0]}.{MIN_PYTHON[1]}+）"
    return False, (f"Python {info[0]}.{info[1]} 太旧，需要 {MIN_PYTHON[0]}.{MIN_PYTHON[1]}+ "
                   f"（tkinter 界面和新语法都需要）")


def check_resolution(size):
    """检查模拟器分辨率。返回 (状态, 说明, 建议)。"""
    want = (1920, 1080)
    if size is None:
        return "warn", "拿不到分辨率", "确认模拟器已启动、adb 能连上"
    if size == want:
        return "ok", "1920x1080 横屏（正确）", ""
    if size == (1080, 1920):
        return "bad", "1080x1920（竖屏）", "把模拟器转成横屏，或在雷电设置里改成平板 1920x1080"
    return "bad", f"{size[0]}x{size[1]}（不是 1920x1080）", \
        "雷电设置 → 性能设置 → 分辨率 选 1920x1080；改完需要重新采集模板"


def check_deps(get_module=None):
    """检查依赖包。返回 [(名字, 是否正常, 版本或错误)]。"""
    if get_module is None:
        def get_module(name):
            mod = __import__(name)
            return getattr(mod, "__version__", "未知")
    out = []
    for name in ("cv2", "numpy"):
        try:
            out.append((name, True, str(get_module(name))))
        except Exception as e:
            out.append((name, False, str(e)))
    try:
        import tkinter  # noqa: F401
        out.append(("tkinter", True, "标准库"))
    except Exception as e:
        out.append(("tkinter", False, str(e)))
    return out


def find_ldplayer():
    """找雷电模拟器的 dnplayer.exe（找不到返回 None）。"""
    for drive in ("C:", "D:", "E:", "F:", "G:"):
        for sub in LDPLAYER_SUBDIRS:
            p = os.path.join(drive + "\\", sub)
            if os.path.exists(p):
                return p
    return None


def missing_templates(exists=None):
    """返回 (缺的必采模板, 缺的车辆模板)。"""
    if exists is None:
        def exists(fname):
            return os.path.exists(os.path.join(config.TEMPLATE_DIR, fname))
    miss_btn = [k for k in config.REQUIRED_TEMPLATES
                if k in config.TEMPLATES and not exists(config.TEMPLATES[k][0])]
    miss_car = [c for c in config.CAR_TEMPLATES if not exists(c + ".png")]
    return miss_btn, miss_car


# ==================== 体检主流程 ====================
def _run_adb(args, timeout=15):
    try:
        p = subprocess.run([config.ADB_PATH] + list(args), capture_output=True,
                           timeout=timeout,
                           creationflags=0x08000000 if os.name == "nt" else 0)
        return p.returncode, p.stdout.decode("utf-8", "ignore")
    except Exception as e:
        return -1, str(e)


def run(verbose=True):
    """跑一遍体检并打印。返回 (是否全部关键项通过, 问题条数)。"""
    lines = []
    problems = []

    def say(mark, title, detail="", hint=""):
        text = f"  {mark} {title}"
        if detail:
            text += f"：{detail}"
        lines.append(text)
        if hint:
            for i, h in enumerate(str(hint).splitlines()):
                lines.append(("        → " if i == 0 else "          ") + h)
        if mark == MARK_BAD:
            problems.append(title)

    lines.append("=" * 56)
    lines.append(f"  环境体检  A9 自动驾驶台 {_version_text()}")
    lines.append("=" * 56)

    # 1) Python
    ok, msg = check_python()
    say(MARK_OK if ok else MARK_BAD, "Python 版本", msg,
        "" if ok else "到 python.org 装 3.10 以上版本（安装时勾选 tcl/tk 和 Add to PATH）")

    # 2) 依赖
    deps = check_deps()
    for name, good, ver in deps:
        say(MARK_OK if good else MARK_BAD, f"依赖 {name}", ver,
            "" if good else "运行 一键配置.bat，或手动执行 pip install -r requirements.txt")

    # 3) adb
    adb_ok = bool(config.ADB_PATH) and (
        os.path.exists(config.ADB_PATH) or shutil.which(config.ADB_PATH))
    if adb_ok:
        say(MARK_OK, "adb", config.ADB_PATH)
    else:
        ld = find_ldplayer()
        if ld:
            # 已经找到雷电了，就直接把该填什么算出来，别让用户自己找
            guess = os.path.join(os.path.dirname(ld), "adb.exe")
            hint = (f"雷电装在 {os.path.dirname(ld)}\n"
                    f"adb.exe 就在同一个目录，把它填进「参数设置 → 设备 → adb 路径」\n"
                    f"（或改 config.py 的 ADB_PATH）：\n"
                    f"{guess}")
        else:
            hint = ("没找到雷电模拟器。到 www.ldmnq.com 装一个，再来跑一次体检\n"
                    "（adb.exe 是雷电自带的，装好就有）")
        say(MARK_BAD, "adb", config.ADB_PATH or "(空)", hint)

    # 4) 设备 / 分辨率 / 游戏
    if adb_ok:
        rc, out = _run_adb(["devices"])
        devices = [l.split("\t")[0] for l in out.splitlines()[1:] if "\tdevice" in l]
        if config.DEVICE_SERIAL in devices:
            say(MARK_OK, "模拟器连接", f"已连接 {config.DEVICE_SERIAL}")
        elif devices:
            say(MARK_BAD, "模拟器连接",
                f"配置的是 {config.DEVICE_SERIAL}，实际连着的是 {'、'.join(devices)}",
                f"把「设备序列号」改成 {devices[0]}\n"
                f"（图形界面：参数设置 → 设备 → 设备序列号；或改 config.py 的 DEVICE_SERIAL）")
        else:
            say(MARK_BAD, "模拟器连接", "没有看到任何设备",
                "先把雷电模拟器启动起来（开机），再跑一次体检")

        rc, out = _run_adb(["shell", "wm", "size"])
        state, msg, hint = check_resolution(parse_wm_size(out))
        say({"ok": MARK_OK, "warn": MARK_WARN, "bad": MARK_BAD}[state], "分辨率", msg, hint)

        rc, out = _run_adb(["shell", "pm", "list", "packages", config.GAME_PACKAGE])
        installed = config.GAME_PACKAGE in out
        say(MARK_OK if installed else MARK_WARN, "游戏安装",
            "已安装" if installed else "没检测到（模拟器里还没装游戏）",
            "" if installed else "在模拟器里装好《狂野飙车9》并登录，再跑脚本")

        rc, out = _run_adb(["shell", "dumpsys", "window"])
        fg = config.GAME_PACKAGE in out
        say(MARK_OK if fg else MARK_WARN, "游戏前台",
            "游戏正在前台" if fg else "游戏不在前台（不影响，脚本会自己启动它）")

    # 5) 模板
    miss_btn, miss_car = missing_templates()
    say(MARK_OK if not miss_btn else MARK_BAD, "按钮模板",
        "齐全" if not miss_btn else "缺 " + "、".join(miss_btn),
        "" if not miss_btn else "双击『采集模板』补采（选择界面标志也要采）")
    say(MARK_OK if not miss_car else MARK_BAD, "车辆模板",
        f"已采 {len(config.CAR_TEMPLATES) - len(miss_car)}/{len(config.CAR_TEMPLATES)} 辆"
        + ("" if not miss_car else "，缺 " + "、".join(miss_car)),
        "" if not miss_car else "双击『采集车辆』，在选车界面把你常用的车卡框下来")

    # 6) 可选文件
    for fname, hint in (("settings.json", "在图形界面里改过参数才会有，正常"),
                        ("python_path.txt", "只有用 exe 启动器且自动找不到 Python 时才需要")):
        p = os.path.join(config.BASE_DIR, fname)
        if os.path.exists(p):
            say(MARK_OK, fname, "存在")

    lines.append("=" * 56)
    if problems:
        lines.append(f"  有 {len(problems)} 项没通过，按上面的 → 提示处理")
    else:
        lines.append("  一切正常，可以开始跑了：双击『启动控制台.bat』打开桌面控制台，"
                     "或『运行脚本.bat』用命令行")

    text = "\n".join(lines)
    if verbose:
        print(text)
    return not problems, len(problems)


def _version_text():
    try:
        from version import VERSION_TEXT
        return VERSION_TEXT
    except Exception:
        return ""


if __name__ == "__main__":
    ok, n = run()
    sys.exit(0 if ok else 1)
