# -*- coding: utf-8 -*-
"""
capture_tool.py —— 采集按钮模板 / 车辆模板 / 屏幕坐标（交互式）

单窗口采集：运行后弹出【一个】图片窗口，所有操作都在这个窗口里完成。
按键：
    d = 下一个          a = 上一个
    Enter/s = 保存框选   n = 刷新截图
    r = 重新框选         q = 退出
流程：先切到对应界面 → 按 n 刷新 → 拖框框住目标 → 回车保存。
"""
import os
import cv2
import numpy as np

import config
from util import ensure_dirs
from adb_helper import ADB, ADBError


def _shot_bgr(adb):
    data = adb.screencap_bytes()
    arr = np.frombuffer(data, np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        raise ADBError("截图解析失败")
    return img


def _capture_loop(adb, items, title):
    """通用单窗口框选采集。items: [(显示名, 文件名, 说明), ...]"""
    total = len(items)
    idx = 0
    img = _shot_bgr(adb)
    rect = None
    start = None

    def path_of(i):
        return os.path.join(config.TEMPLATE_DIR, items[i][1])

    def describe(i):
        name, fname, desc = items[i]
        ok = "已采集" if os.path.exists(path_of(i)) else "未采集"
        return f"[{i + 1}/{total}] {name}  ({ok})   {desc}"

    print("=" * 58)
    print(f"{title}（单窗口操作）")
    print("按键：d=下一个  a=上一个  Enter/s=保存  n=刷新  r=重框  q=退出")
    print("步骤：切到对应界面 -> 按 n 刷新 -> 拖框框住目标 -> 回车保存")
    print("=" * 58)
    print("当前: " + describe(idx))

    cv2.namedWindow(title, cv2.WINDOW_NORMAL)

    def on_mouse(event, x, y, flags, param):
        nonlocal rect, start
        if event == cv2.EVENT_LBUTTONDOWN:
            start = (x, y)
            rect = (x, y, x, y)
        elif event == cv2.EVENT_MOUSEMOVE and start:
            rect = (start[0], start[1], x, y)
        elif event == cv2.EVENT_LBUTTONUP and start:
            x0, y0 = start
            rect = (min(x0, x), min(y0, y), max(x0, x), max(y0, y))
            start = None

    cv2.setMouseCallback(title, on_mouse)

    def overlay(base):
        d = base.copy()
        h, w = d.shape[:2]
        name, fname, desc = items[idx]
        ok = "OK" if os.path.exists(path_of(idx)) else "MISSING"
        line1 = f"[{idx + 1}/{total}] {name}  {ok}"
        line2 = "d:next  a:prev  Enter/s:save  n:refresh  r:reset  q:quit"
        band = d.copy()
        cv2.rectangle(band, (0, 0), (w, 58), (30, 30, 30), -1)
        d = cv2.addWeighted(band, 0.55, d, 0.45, 0)
        cv2.putText(d, line1, (16, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 255), 2, cv2.LINE_AA)
        band = d.copy()
        cv2.rectangle(band, (0, h - 42), (w, h), (30, 30, 30), -1)
        d = cv2.addWeighted(band, 0.55, d, 0.45, 0)
        cv2.putText(d, line2, (16, h - 14), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 200), 1, cv2.LINE_AA)
        if rect and rect[2] > rect[0] and rect[3] > rect[1]:
            cv2.rectangle(d, (rect[0], rect[1]), (rect[2], rect[3]), (0, 255, 0), 3)
        return d

    while True:
        cv2.imshow(title, overlay(img))
        k = cv2.waitKey(20) & 0xFF
        if k == ord('q'):
            break
        elif k == ord('d'):
            idx = (idx + 1) % total
            rect = None
            start = None
            print("当前: " + describe(idx))
        elif k == ord('a'):
            idx = (idx - 1) % total
            rect = None
            start = None
            print("当前: " + describe(idx))
        elif k == ord('n'):
            try:
                img = _shot_bgr(adb)
                rect = None
                start = None
                print("[已刷新截图] " + describe(idx))
            except ADBError as e:
                print("刷新失败:", e)
        elif k == ord('r'):
            rect = None
            start = None
        elif k in (13, ord('s')):
            if rect and rect[2] > rect[0] and rect[3] > rect[1]:
                x0, y0, x1, y1 = rect
                if x1 - x0 < 6 or y1 - y0 < 6:
                    print("框选太小，已忽略")
                else:
                    name, fname, desc = items[idx]
                    out = os.path.join(config.TEMPLATE_DIR, fname)
                    crop = img[y0:y1, x0:x1]
                    cv2.imwrite(out, crop)
                    print(f"[已保存] {name} -> {fname}  ({x1 - x0}x{y1 - y0})")
                    # 即时验证：重新截图，当场测这张模板在当前屏的匹配度
                    try:
                        c = _shot_bgr(adb)
                        cg = cv2.cvtColor(c, cv2.COLOR_BGR2GRAY)
                        tg = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
                        if cg.shape[0] >= tg.shape[0] and cg.shape[1] >= tg.shape[1]:
                            r = cv2.matchTemplate(cg, tg, cv2.TM_CCOEFF_NORMED)
                            cmax = float(cv2.minMaxLoc(r)[1])
                            if cmax >= 0.85:
                                print(f"  [验证] 当前屏匹配 {cmax:.3f}  √ 很好")
                            elif cmax >= 0.70:
                                print(f"  [验证] 当前屏匹配 {cmax:.3f}  △ 偏弱，建议框更紧/只框稳定部分")
                            else:
                                print(f"  [验证] 当前屏匹配 {cmax:.3f}  × 没对上！可能框错或框了会动的部分，请重新框")
                    except ADBError as e:
                        print("  [验证] 截图失败:", e)
                    print("当前: " + describe(idx))
                rect = None
                start = None
            else:
                print("请先用鼠标拖一个框")
    cv2.destroyAllWindows()

    print("\n===== 采集汇总 =====")
    missing = [items[i][0] for i in range(total) if not os.path.exists(path_of(i))]
    if not missing:
        print("全部采集完成")
    else:
        print("还缺:", ", ".join(missing))


def capture_templates():
    """采集按钮模板（config.TEMPLATES）。"""
    ensure_dirs()
    adb = ADB()
    items = [(k, fn, desc) for k, (fn, desc) in config.TEMPLATES.items()]
    _capture_loop(adb, items, "template-capture")
    req_missing = [k for k in config.REQUIRED_TEMPLATES
                   if not os.path.exists(os.path.join(config.TEMPLATE_DIR, config.TEMPLATES[k][0]))]
    if req_missing:
        print("【必采项还缺】:", ", ".join(req_missing))
    else:
        print("必采项齐全，可以运行脚本了")


def capture_cars():
    """采集车辆车卡图片（config.CAR_TEMPLATES，主车在前、备用车在后）。"""
    ensure_dirs()
    adb = ADB()
    items = []
    for name in config.CAR_TEMPLATES:
        items.append((name, name + ".png", "车辆车卡：框这辆车本身（别框状态图标）"))
    _capture_loop(adb, items, "car-capture")
    captured = [name for name in config.CAR_TEMPLATES
                if os.path.exists(os.path.join(config.TEMPLATE_DIR, name + ".png"))]
    print("\n已采集车辆:", captured)
    print("config.CAR_TEMPLATES 顺序（主车在前、备用车在后）:", config.CAR_TEMPLATES)


def capture_coords():
    """点击画面取坐标（通用，按 q 打印结果）。"""
    ensure_dirs()
    adb = ADB()
    points = []
    img = _shot_bgr(adb)

    def cb(event, x, y, flags, param):
        if event == cv2.EVENT_LBUTTONDOWN:
            points.append((x, y))
            print(f"  点 {len(points)}: ({x}, {y})")

    win = "coords"
    cv2.namedWindow(win, cv2.WINDOW_NORMAL)
    cv2.setMouseCallback(win, cb)
    print("坐标采集：左键点击记点；n=刷新  u=撤销上一点  q/Esc=结束")
    while True:
        disp = img.copy()
        for p in points:
            cv2.circle(disp, p, 8, (0, 0, 255), 2)
        cv2.imshow(win, disp)
        k = cv2.waitKey(20) & 0xFF
        if k == ord('n'):
            img = _shot_bgr(adb)
            points = []
            print("已刷新，重新记点")
        elif k == ord('u') and points:
            points.pop()
            print("撤销上一点")
        elif k in (ord('q'), 27):
            break
    cv2.destroyAllWindows()
    print("\n===== 采集结果 =====")
    if points:
        print("坐标列表：")
        for p in points:
            print(f"    ({p[0]}, {p[1]}),")
    else:
        print("未采集到任何点")
