# -*- coding: utf-8 -*-
"""setup_env.py —— 一键配置环境（由 一键配置.bat 调用）

做四件事：
  1. 检查 Python 版本、装依赖（opencv-python / numpy）
  2. 检查 tkinter（图形界面要用）
  3. 跑一遍环境体检（doctor.py）
  4. 打印接下来该干什么

只管「装和查」，不会动游戏、不会动模拟器设置。
"""
import os
import subprocess
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MIRROR = "https://pypi.tuna.tsinghua.edu.cn/simple"       # 国内镜像，装得快
REQ = os.path.join(BASE_DIR, "requirements.txt")

MIN_PY = (3, 10)
STEP = "─" * 56


def title(text):
    print("\n" + STEP)
    print("  " + text)
    print(STEP)


def run_pip(extra):
    """跑一次 pip，返回是否成功。"""
    cmd = [sys.executable, "-m", "pip", "install", "--disable-pip-version-check"] + extra
    print("  > " + " ".join(cmd))
    try:
        return subprocess.call(cmd) == 0
    except Exception as e:
        print(f"  ! 执行失败：{e}")
        return False


def install_deps():
    title("第 1 步 / 3：安装依赖")
    if not os.path.exists(REQ):
        print(f"  ! 找不到 {REQ}")
        return False

    # 先试国内镜像，失败再试官方源
    for extra, label in ((["-r", REQ, "-i", MIRROR], "清华镜像"),
                         (["-r", REQ], "官方源")):
        print(f"\n  使用{label} ...")
        if run_pip(extra):
            print("  √ 依赖已就绪")
            return True
        print(f"  ! {label}没成功，换下一个试试")

    print("\n  × 依赖安装失败。检查一下网络，或者手动执行：")
    print(f"      {sys.executable} -m pip install -r requirements.txt")
    return False


def check_tkinter():
    title("第 2 步 / 3：检查图形界面组件")
    try:
        import tkinter  # noqa: F401
        print("  √ tkinter 可用（桌面控制台能打开）")
        return True
    except Exception as e:
        print(f"  × tkinter 不可用：{e}")
        print("    tkinter 是 Python 自带的组件，装 Python 时要勾上 “tcl/tk and IDLE”。")
        print("    修不了也不影响命令行运行：可以只用 python main.py run。")
        return False


def write_python_path():
    """把当前 Python 的路径记到 python_path.txt。

    exe 启动器（Releases 里那个 zip）找 Python 的顺序是：
    python_path.txt → PATH → 常见安装位置。
    这里提前写好，用户下载 exe 后就不用自己填路径了。
    """
    p = os.path.join(BASE_DIR, "python_path.txt")
    cur = ""
    if os.path.exists(p):
        try:
            with open(p, encoding="utf-8-sig") as f:
                cur = f.read().strip()
        except Exception:
            cur = ""
    if cur == sys.executable:
        return
    try:
        with open(p, "w", encoding="utf-8") as f:
            f.write(sys.executable)
        print(f"  √ 已记录 Python 路径（exe 启动器会用它）：{sys.executable}")
    except Exception as e:
        print(f"  ! 写 python_path.txt 失败（不影响使用）：{e}")


def main():
    print("=" * 56)
    print("  A9 自动驾驶台 —— 一键配置环境")
    print("=" * 56)
    print(f"  Python : {sys.version.split()[0]}")
    print(f"  位置   : {sys.executable}")
    print(f"  目录   : {BASE_DIR}")

    if sys.version_info[:2] < MIN_PY:
        print(f"\n  × Python 版本太低，需要 {MIN_PY[0]}.{MIN_PY[1]} 以上。")
        print("    到 https://www.python.org/downloads/ 装新版，安装时勾选")
        print("    “Add python.exe to PATH” 和 “tcl/tk and IDLE”，然后再运行一次。")
        return 1

    ok_deps = install_deps()
    check_tkinter()
    write_python_path()

    title("第 3 步 / 3：环境体检")
    try:
        import doctor
        all_ok, n = doctor.run()
    except Exception as e:
        print(f"  ! 体检没跑起来：{e}")
        all_ok, n = False, 1

    title("接下来做什么")
    if not ok_deps or not all_ok:
        print("  先按上面带 → 的提示把问题处理掉，再回来跑一次本脚本。")
    else:
        print("  1. 打开雷电模拟器，把游戏开到任意界面（脚本会自己认界面接着跑）")
        print("  2. 双击『采集车辆』，在选车界面把你常用的车卡框下来")
        print("     （按钮模板已经随仓库提供，一般不用重采）")
        print("  3. 双击『启动控制台.bat』打开桌面控制台，点「启动脚本」就行了")
        print("     （想用命令行也可以：python main.py run）")
    print()
    return 0 if (ok_deps and all_ok) else 1


if __name__ == "__main__":
    sys.exit(main())
