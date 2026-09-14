# -*- coding: utf-8 -*-
"""
settings_io.py —— 可编辑参数表 + 读写（桌面版 / 网页版共用）

前端只读写 settings.json，config.py 保持默认值；
保存后调用 config.reload_settings() 让新值生效。
"""
import json
import os

import config
from util import log

# 可编辑参数表：桌面版和网页版都据此渲染表单
SETTINGS_SCHEMA = [
    {"key": "NITRO_X", "label": "氮气 X 坐标", "group": "氮气", "type": "int", "hint": "氮气按钮横坐标"},
    {"key": "NITRO_Y", "label": "氮气 Y 坐标", "group": "氮气", "type": "int", "hint": "氮气按钮纵坐标"},
    {"key": "NITRO_INTERVAL_S", "label": "氮气间隔(秒)", "group": "氮气", "type": "int", "hint": "比赛中每隔多少秒双击一次"},
    {"key": "NITRO_GAP_MIN_MS", "label": "双击最小间隔(毫秒)", "group": "氮气", "type": "int", "hint": "两次点击之间最小间隔"},
    {"key": "NITRO_GAP_MAX_MS", "label": "双击最大间隔(毫秒)", "group": "氮气", "type": "int", "hint": "两次点击之间最大间隔"},

    {"key": "MATCH_THRESHOLD", "label": "图像识别阈值", "group": "识别", "type": "float",
     "hint": "0~1，越大越严格；识别不到就调小", "min": 0.5, "max": 1.0, "step": 0.01},
    {"key": "CAR_MATCH_THRESHOLD", "label": "车辆识别阈值", "group": "识别", "type": "float",
     "hint": "车辆单独用更严的阈值（默认0.92）。调低容易把别的车当成目标车",
     "min": 0.5, "max": 1.0, "step": 0.01},
    {"key": "CAR_MATCH_MIN_MARGIN", "label": "车辆防误判差值", "group": "识别", "type": "float",
     "hint": "最佳位置要比次佳高出这么多才算数（默认0.05），防止外观相似的车干扰",
     "min": 0.0, "max": 0.5, "step": 0.01},

    {"key": "MATCHING_DELAY_S", "label": "匹配等待(秒)", "group": "超时", "type": "int", "hint": "点开始匹配后固定等待的时间"},
    {"key": "RACE_TIMEOUT_S", "label": "单场超时(秒)", "group": "超时", "type": "int", "hint": "超过则视为异常继续"},
    {"key": "POST_RACE_TIMEOUT_S", "label": "赛后弹窗超时(秒)", "group": "超时", "type": "int", "hint": "处理里程碑/段位弹窗的最长时间"},
    {"key": "POST_RACE_STABLE_CHECKS", "label": "回主界面确认次数", "group": "超时", "type": "int",
     "hint": "连续几次没弹窗才算真的回到主界面（防止弹窗还没加载出来就结束）"},
    {"key": "POST_RACE_STABLE_INTERVAL_S", "label": "确认间隔(秒)", "group": "超时", "type": "int",
     "hint": "每次确认之间的等待秒数"},
    {"key": "GAME_START_WAIT_S", "label": "重启加载等待(秒)", "group": "超时", "type": "int", "hint": "重启游戏后等待加载完成的时间"},
    {"key": "GAME_START_TIMEOUT_S", "label": "游戏启动超时(秒)", "group": "超时", "type": "int", "hint": "等待主界面的最长时间"},

    {"key": "MATCH_ERROR_TAP", "label": "错误弹窗×坐标", "group": "匹配", "type": "coord",
     "hint": "留空则按模板位置自动推算；填了就固定用它"},
    {"key": "MATCH_ERROR_X_OFFSET", "label": "×横向偏移", "group": "匹配", "type": "int",
     "hint": "× 相对 match_error 模板中心的横向偏移"},
    {"key": "MATCH_ERROR_Y_OFFSET", "label": "×纵向偏移", "group": "匹配", "type": "int",
     "hint": "× 相对 match_error 模板中心的纵向偏移"},

    {"key": "MATCH_ERROR_CHECK_S", "label": "查错误弹窗间隔(秒)", "group": "截图频率", "type": "int",
     "hint": "匹配阶段每隔几秒截图查一次错误弹窗（调大更省 CPU）"},
    {"key": "RACE_START_QUIET_S", "label": "开局不截图(秒)", "group": "截图频率", "type": "int",
     "hint": "比赛开始后前 N 秒不截图（赛道加载期间，截图易压崩游戏）"},

    {"key": "RELAUNCH_TAP", "label": "重启后点击坐标", "group": "闪退恢复", "type": "coord",
     "hint": "重启游戏后点一下才能回主界面的坐标，填 x,y"},
    {"key": "RELAUNCH_MAX_ATTEMPTS", "label": "最大连续重启次数", "group": "闪退恢复", "type": "int",
     "hint": "一次恢复最多连续重启几次（加载界面再闪退会自动重来）"},
    {"key": "RELAUNCH_FOREGROUND_WAIT_S", "label": "等进前台(秒)", "group": "闪退恢复", "type": "int",
     "hint": "启动后等待游戏进入前台的秒数"},
    {"key": "RELAUNCH_QUIET_S", "label": "静默不截图(秒)", "group": "闪退恢复", "type": "int",
     "hint": "重启后前 N 秒不截图（截图会把加载中的游戏压崩）"},
    {"key": "RELAUNCH_LOAD_TIMEOUT_S", "label": "等登陆标志(秒)", "group": "闪退恢复", "type": "int",
     "hint": "静默期结束后，等待『登陆成功标志』出现的最长时间"},

    {"key": "CAR_TEMPLATES", "label": "车辆列表", "group": "选车", "type": "list",
     "hint": "每行一个车辆模板名，主车在前、备用车在后", "hidden": True},

    {"key": "REWARD_MODE", "label": "奖励选择方式", "group": "动态奖励", "type": "choice",
     "options": [("auto", "自动选"), ("manual", "弹窗提醒我选")],
     "hint": "出现「动态奖励」时：自动挑第 N 张，还是弹窗提醒你自己选"},
    {"key": "REWARD_PICK_INDEX", "label": "自动选第几张", "group": "动态奖励", "type": "int",
     "hint": "1~5（第 6 张在屏幕外）；仅「自动选」模式有效"},
    {"key": "REWARD_MANUAL_TIMEOUT_S", "label": "手动等待(秒)", "group": "动态奖励", "type": "int",
     "hint": "手动模式下等你自己选的时间，超时先继续跑"},

    {"key": "MAX_LOOPS", "label": "循环次数", "group": "循环", "type": "int", "hint": "0 = 无限循环"},

    {"key": "DEVICE_SERIAL", "label": "设备序列号", "group": "设备", "type": "str", "hint": "如 emulator-5554"},
    {"key": "ADB_PATH", "label": "adb 路径", "group": "设备", "type": "str", "hint": "雷电模拟器 adb.exe 绝对路径"},
]


def current_settings():
    out = {}
    for item in SETTINGS_SCHEMA:
        key = item["key"]
        val = getattr(config, key, None)
        t = item["type"]
        if t == "list":
            val = val if isinstance(val, list) else []
        elif t == "coord":
            val = "" if not val else "{},{}".format(val[0], val[1])
        out[key] = val
    return out


def _coerce(item, v):
    t = item["type"]
    if t == "int":
        return int(float(v))
    if t == "float":
        return float(v)
    if t == "str":
        return str(v)
    if t == "choice":
        # 只能取 options 里列出的值，写别的就退回第一项
        opts = [o[0] for o in item.get("options", [])]
        s = str(v).strip()
        if s in opts:
            return s
        return opts[0] if opts else s
    if t == "list":
        if isinstance(v, list):
            return [str(x).strip() for x in v if str(x).strip()]
        if isinstance(v, str):
            return [x.strip() for x in v.splitlines() if x.strip()]
        return []
    if t == "coord":
        if v is None:
            return None
        s = str(v).strip()
        if not s:
            return None
        parts = s.replace("，", ",").replace(" ", ",").split(",")
        parts = [p for p in parts if p.strip() != ""]
        if len(parts) < 2:
            return None
        return (int(float(parts[0])), int(float(parts[1])))
    return v


def save_settings(data):
    clean = {}
    for item in SETTINGS_SCHEMA:
        key = item["key"]
        if key not in data:
            continue
        try:
            clean[key] = _coerce(item, data[key])
        except (ValueError, TypeError):
            continue

    path = os.path.join(config.BASE_DIR, "settings.json")
    # 合并写入：只改一部分参数时（比如只增删车辆）不会把别的设置冲掉
    merged = {}
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                old = json.load(f)
            if isinstance(old, dict):
                merged.update(old)
    except Exception:
        pass
    merged.update(clean)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=False, indent=2)
    config.reload_settings()
    log("参数已保存到 settings.json")
    return merged
