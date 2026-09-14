# -*- coding: utf-8 -*-
"""
main.py —— 命令行入口

用法：
  python main.py run             运行主循环
  python main.py check           环境自检
  python main.py capture         采集按钮模板
  python main.py coords          采集屏幕坐标
  python main.py snap            截一张图保存到 shots/
  python main.py test <key>      测试某个模板在当前屏幕的匹配结果
"""
import argparse
import os

import config
from util import log, ensure_dirs
from version import VERSION_TEXT


def cmd_check():
    """环境体检：Python / 依赖 / adb / 模拟器 / 分辨率 / 游戏 / 模板 全查一遍。"""
    import doctor
    ensure_dirs()

    ok, problems = doctor.run()

    # 体检之后再列出模板明细，方便定位是哪一个没采
    from vision import Vision
    vis = Vision()
    print("\n  模板明细：")
    for key, (fname, desc) in config.TEMPLATES.items():
        mark = "√" if vis.template_exists(key) else "×"
        need = "必采" if key in config.REQUIRED_TEMPLATES else "可选"
        print(f"    [{mark}] {key:20s} {fname:26s} {need}  {desc}")
    print(f"\n  氮气坐标: ({config.NITRO_X}, {config.NITRO_Y})")
    print(f"  车辆模板: {config.CAR_TEMPLATES}")
    return 0 if ok else 1



def cmd_run():
    from bot import GameBot
    GameBot().run()


def cmd_capture():
    from capture_tool import capture_templates
    capture_templates()


def cmd_coords():
    from capture_tool import capture_coords
    capture_coords()


def cmd_capture_car():
    from capture_tool import capture_cars
    capture_cars()


def cmd_snap():
    from adb_helper import ADB
    ensure_dirs()
    p = ADB().screencap_file()
    print("截图已保存:", p)


def cmd_test(key, threshold):
    from adb_helper import ADB
    from vision import Vision
    import cv2
    import numpy as np
    ensure_dirs()
    adb = ADB()
    vis = Vision()
    tpl = vis.load_template(key)
    if tpl is None:
        print(f"模板不存在: {key}")
        return
    data = adb.screencap_bytes()
    bgr = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    res = cv2.matchTemplate(gray, tpl, cv2.TM_CCOEFF_NORMED)
    _, maxv, _, maxloc = cv2.minMaxLoc(res)
    h, w = tpl.shape
    top = maxloc
    bottom = (maxloc[0] + w, maxloc[1] + h)
    cv2.rectangle(bgr, top, bottom, (0, 0, 255), 2)
    out = os.path.join(config.SHOT_DIR, f"test_{key}.png")
    cv2.imwrite(out, bgr)
    th = threshold if threshold is not None else config.MATCH_THRESHOLD
    print(f"[{key}] 置信度={maxv:.3f} (阈值 {th}) {'√ 命中' if maxv >= th else '× 未命中'}")
    print(f"  中心坐标=({maxloc[0] + w // 2}, {maxloc[1] + h // 2})")
    print(f"  标注图: {out}")


def main():
    parser = argparse.ArgumentParser(
        description=f"狂野飙车9 自动脚本 A9 自动驾驶台 {VERSION_TEXT}")
    sub = parser.add_subparsers(dest="cmd")

    sub.add_parser("run", help="运行主循环")
    sub.add_parser("check", help="环境自检")
    sub.add_parser("capture", help="采集按钮模板")
    sub.add_parser("capture_car", help="采集车辆模板")
    sub.add_parser("coords", help="采集屏幕坐标")
    sub.add_parser("snap", help="截一张图保存")

    p_test = sub.add_parser("test", help="测试某个模板在当前屏幕的匹配结果")
    p_test.add_argument("key", help="模板逻辑名，如 mode_entry")
    p_test.add_argument("--threshold", type=float, default=None, help="临时置信度阈值")

    args = parser.parse_args()
    if args.cmd is None:
        parser.print_help()
        return
    if args.cmd == "run":
        cmd_run()
    elif args.cmd == "check":
        cmd_check()
    elif args.cmd == "capture":
        cmd_capture()
    elif args.cmd == "capture_car":
        cmd_capture_car()
    elif args.cmd == "coords":
        cmd_coords()
    elif args.cmd == "snap":
        cmd_snap()
    elif args.cmd == "test":
        cmd_test(args.key, args.threshold)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log("已停止")
