# -*- coding: utf-8 -*-
"""build_launcher.py —— 编译 exe 启动器（由 build_launcher.bat 调用）

为什么要用 Python 而不是直接写在 bat 里：
    exe 的文件名是中文（采集模板.exe 等），而 .bat 里的中文会被 cmd 按系统
    代码页（中文系统是 936）解析乱掉，导致脚本报奇怪的错。
    Python 处理中文路径没有任何问题，所以批处理只留一行调用，逻辑放这里。

什么时候需要跑：只有改了 launcher.cs 才需要。
改了 gui.py / bot.py 等 Python 文件是即时生效的，不用重新编译。
"""
import locale
import os
import subprocess
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def decode_output(data):
    """csc 的报错是系统本地编码（中文系统是 GBK）。

    直接用 utf-8 解会把这些中文丢掉（errors="ignore"），用户就看到一条空报错，
    所以按「utf-8 → 系统编码 → gbk」依次试。
    """
    if not data:
        return ""
    for enc in ("utf-8", locale.getpreferredencoding(False), "gbk"):
        if not enc:
            continue
        try:
            return data.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return data.decode("utf-8", "replace")


CSC_CANDIDATES = (
    os.path.join(os.environ.get("WINDIR", r"C:\Windows"),
                 r"Microsoft.NET\Framework64\v4.0.30319\csc.exe"),
    os.path.join(os.environ.get("WINDIR", r"C:\Windows"),
                 r"Microsoft.NET\Framework\v4.0.30319\csc.exe"),
)
# (输出文件名, 额外编译参数)
TARGETS = (
    ("A9控制台.exe", ["/target:winexe", "/define:WINDOWLESS"]),
    ("采集模板.exe", ["/target:exe"]),
    ("采集车辆.exe", ["/target:exe"]),
    ("采集坐标.exe", ["/target:exe"]),
    ("环境自检.exe", ["/target:exe"]),
)


def find_csc():
    for p in CSC_CANDIDATES:
        if os.path.exists(p):
            return p
    return None


def main():
    print("=" * 56)
    print("  编译 exe 启动器")
    print("=" * 56)

    csc = find_csc()
    if csc is None:
        print("  × 找不到 C# 编译器 csc.exe（.NET Framework 4 一般随 Windows 自带）")
        print("    找不到也没关系：exe 只是方便双击，直接跑 python gui.py 一样能用。")
        return 1
    src = os.path.join(BASE_DIR, "launcher.cs")
    if not os.path.exists(src):
        print(f"  × 找不到 {src}")
        return 1

    print(f"  编译器: {csc}")
    icon = os.path.join(BASE_DIR, "icon.ico")
    base_args = ["/nologo", "/codepage:65001"]
    if os.path.exists(icon):
        base_args.append("/win32icon:" + icon)

    failed = 0
    for name, extra in TARGETS:
        out = os.path.join(BASE_DIR, name)
        if os.path.exists(out):
            try:                      # 被占用（比如控制台正开着）时早点说清楚
                with open(out, "ab"):
                    pass
            except OSError:
                print(f"  × {name}：文件正被占用，先关掉它再重新编译")
                failed += 1
                continue
        cmd = [csc] + base_args + extra + ["/out:" + out, src]
        r = subprocess.run(cmd, capture_output=True)
        if r.returncode == 0:
            print(f"  √ {name}")
        else:
            failed += 1
            print(f"  × {name}")
            err = (decode_output(r.stdout) + decode_output(r.stderr)).strip()
            if err:
                print("    " + err.replace("\n", "\n    "))

    print("=" * 56)
    if failed:
        print(f"  有 {failed} 个编译失败，看上面的报错")
        return 1
    print("  全部编译完成。")
    print("  提示：exe 需要能找到 Python；自动找不到时，在本目录放一个")
    print("        python_path.txt，里面写 python.exe 的完整路径。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
