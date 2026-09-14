# -*- coding: utf-8 -*-
"""
config.py —— 全局配置（所有可调参数都集中在这里）

首次使用请按顺序：
  1. python main.py check       —— 环境自检（确认 adb / 设备 / 模板缺失情况）
  2. python main.py capture     —— 采集按钮模板图片
  3. python main.py capture_car —— 采集车辆车卡图片（选车用，主车在前、备用车在后）
  4. python main.py run         —— 开始运行
"""

import os
import sys

if getattr(sys, "frozen", False):
    # PyInstaller 打包后：以 exe 所在目录作为数据目录（templates / settings.json 放这里）
    BASE_DIR = os.path.dirname(os.path.abspath(sys.executable))
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ==================== 雷电模拟器 / ADB ====================
def _find_adb():
    """自动找 adb.exe，省得每个人都要手改路径。

    顺序：环境变量 → 各盘常见安装位置 → PATH 里的 adb。
    都没找到就返回 "adb"（交给系统 PATH 解析）。
    想固定用它，写进 settings.json 的 ADB_PATH 即可（会覆盖这里）。
    """
    import shutil

    cands = []
    for env in ("LDPLAYER_ADB", "ADB_PATH", "ANDROID_HOME"):
        v = os.environ.get(env)
        if not v:
            continue
        if v.lower().endswith(".exe"):
            cands.append(v)
        else:
            cands.append(os.path.join(v, "adb.exe"))
            cands.append(os.path.join(v, "platform-tools", "adb.exe"))

    subdirs = (
        r"leidian\LDPlayer14\adb.exe",
        r"leidian\LDPlayer9\adb.exe",
        r"雷电模拟器\leidian\LDPlayer14\adb.exe",
        r"雷电模拟器\leidian\LDPlayer9\adb.exe",
        r"雷电模拟器9\leidian\LDPlayer9\adb.exe",
        r"LDPlayer\LDPlayer14\adb.exe",
        r"LDPlayer\LDPlayer9\adb.exe",
        r"Program Files\LDPlayer\LDPlayer14\adb.exe",
    )
    for drive in ("C:", "D:", "E:", "F:", "G:"):
        for sub in subdirs:
            cands.append(os.path.join(drive + "\\", sub))

    on_path = shutil.which("adb")
    if on_path:
        cands.append(on_path)

    for c in cands:
        try:
            if c and os.path.exists(c):
                return c
        except OSError:
            pass
    return "adb"          # 交给 PATH 解析


ADB_PATH = _find_adb()

# 设备序列号：实例0 → emulator-5554；第二个实例通常是 emulator-5556
# 不确定时在命令行执行 adb devices 查看
DEVICE_SERIAL = "emulator-5554"

# ==================== 游戏 ====================
GAME_PACKAGE  = "com.aligames.kuang.kybc.tap"               # 狂野飙车9 包名
GAME_ACTIVITY = "com.aligames.kuang.kybc.tap/.MainActivity" # 启动 Activity
GAME_START_TIMEOUT_S = 120   # 重启游戏后，等待主界面出现的最大秒数（游戏加载较慢）
GAME_START_WAIT_S = 40       # 重启游戏后，等待游戏加载完成的时间（秒）
RELAUNCH_TAP = (529, 467)    # 加载完成后需点击一次的坐标，才能回到主界面

# ==================== 目录 ====================
TEMPLATE_DIR = os.path.join(BASE_DIR, "templates")   # 按钮模板图
SHOT_DIR     = os.path.join(BASE_DIR, "shots")       # 截图 / 调试输出

# ==================== 识别 ====================
MATCH_THRESHOLD = 0.82     # 模板匹配置信度阈值(0~1)，越大越严格、越不易误判
POLL_INTERVAL_S = 1.0      # 轮询间隔(秒)
SAVE_DEBUG_SHOTS = False   # 是否保存每一帧截图到 shots/（调试用，长期运行请关闭）

# 单个模板的置信度阈值覆盖（默认用上面的 MATCH_THRESHOLD）
TEMPLATE_THRESHOLDS = {
    "mode_entry": 0.72,   # 主界面『开始』按钮对比度低，单独放宽
    # 模式卡片里含「评级分」数字（跑一场会变），放宽一点更稳；
    # 其它界面上它只有 0.29~0.39，所以放到 0.75 也不会误判
    "mode_card": 0.75,
}

# ==================== 氮气（双击） ====================
# 氮气按钮坐标 —— 直接按坐标双击氮气（不再用模板）。
# 1920x1080 横向画面，氮气通常在右下角；把实际坐标填到下面两行即可。
NITRO_X = 1624
NITRO_Y = 809
NITRO_INTERVAL_S  = 18      # 比赛中每隔多少秒双击一次
NITRO_GAP_MIN_MS  = 570     # 两次点击之间的最小间隔(毫秒)
NITRO_GAP_MAX_MS  = 590     # 两次点击之间的最大间隔(毫秒)

# ==================== 超时 ====================
MATCHING_DELAY_S   = 20     # 点完详情页『开始』后固定等待这段时间（匹配耗时，不做图片判断）
RACE_TIMEOUT_S     = 600    # 单场比赛最长时长(秒)，超过视为异常并继续后续流程
POST_RACE_TIMEOUT_S = 90    # 赛后处理弹窗的最长时间(秒)
# 赛后切回主界面时，主界面会【先】渲染出来，里程碑/段位弹窗是随后才加载的。
# 所以不能一看到主界面就结束，要连续确认几次都没有弹窗才算真的结束。
POST_RACE_STABLE_CHECKS = 3      # 连续确认多少次没弹窗才算结束
POST_RACE_STABLE_INTERVAL_S = 2  # 每次确认之间的间隔(秒)

# ==================== 匹配错误弹窗 ====================
# 匹配时连不上服务器会弹错误框，识别到后点右上角 × 关闭。
# × 的坐标默认由 match_error 模板匹配到的位置自动推算（弹窗挪位置也能点中）；
# 想写死绝对坐标就填 MATCH_ERROR_TAP。
#
# 注意：关掉弹窗后游戏会【退回选车界面】（实测：日志里那句
# 「没找到『开始』按钮，无法重新发起匹配」就是旧代码踩的坑 ——
# 它以为还在详情页，而『开始』只存在于详情页）。
# 所以重新发起匹配必须先重新选一次车，逻辑在 bot.py 的 retry_match()。
MATCH_ERROR_TAP = None        # 备用：× 的绝对坐标，例如 (1610, 65)
MATCH_ERROR_X_OFFSET = 650    # × 相对 match_error 模板中心的横向偏移
MATCH_ERROR_Y_OFFSET = 0      # × 相对 match_error 模板中心的纵向偏移
                              # （这两个偏移是按当前「标题栏+×」模板量的，
                              #   如果重新采集的模板换了个框法，需要重新量）
MATCH_ERROR_MAX_RETRIES = 5   # 一场比赛内最多重新发起几次匹配（防服务器一直挂时死循环）

# ==================== 闪退恢复 ====================
# 闪退后可能一次重启不成功（在加载界面又闪退），这里控制自动重试
RELAUNCH_MAX_ATTEMPTS = 4        # 一次恢复最多连续重启几次
RELAUNCH_FOREGROUND_WAIT_S = 25  # 重启后等待游戏进入前台的秒数
RELAUNCH_QUIET_S = 75            # 重启后前 N 秒【不截图】（截图会把加载中的游戏压崩）
RELAUNCH_LOAD_TIMEOUT_S = 120    # 静默期后，等待「登陆成功标志」的最长时间

# ==================== 截图频率控制 ====================
# 截图(screencap)要在模拟器里做 PNG 编码，很吃 CPU。
# 「游戏正在加载」的阶段频繁截图会把游戏压崩（实测加载时每秒截图必崩），
# 所以这些阶段要拉长间隔甚至完全不截。
MATCH_ERROR_CHECK_S = 3     # 匹配阶段每隔几秒查一次错误弹窗（越小越灵敏、越吃 CPU）
RACE_START_QUIET_S = 20     # 比赛开始后前 N 秒不截图（赛道加载期间）

# ==================== 选车（按车辆图片识别） ====================
# 把每辆车的车卡截图保存为 templates/car_1.png, car_2.png, ...
# 脚本按顺序用图像匹配找到车并点击；没油就返回试下一辆。
# 用 python main.py capture_car 采集（或双击「采集车辆.bat」）。
# 有几辆车就保留几个（可增删），按你想优先选用的顺序排列。
CAR_TEMPLATES = [
    "car_1",
    "car_2",
]

# 车辆匹配单独用更严格的阈值（不要用 MATCH_THRESHOLD）。
# 原因（实测数据）：车卡模板里有一大片「所有车都长一样」的装饰——稀有度底色、
# 右边的图纸海报、『最高』角标、油量角标。所以把 A 车的模板拿去匹 B 车的卡，
# 也能匹到 0.81~0.83。实测：
#     A 车在场            → 0.9924（正确位置）
#     A 车不在场，匹到 B 车 → 0.8255（错误位置）
# 如果阈值还是 0.82，一旦目标车不在当前画面，脚本就会把别的车当目标车点下去
# ——这就是「选车选到别的车」。真车 0.99 / 假车 0.83，所以把阈值提到 0.92。
CAR_MATCH_THRESHOLD = 0.92

# 歧义保护：最佳位置还要比「第二好的、互不重叠的位置」高出这么多才算数。
# 防止两辆外观相似的车（同稀有度、同厂牌）互相干扰时乱点。
CAR_MATCH_MIN_MARGIN = 0.05

# ---------- 选车界面「等画面静止」 ----------
# 实测真相：进入选车界面后，车辆列表会横向滑动好几秒（约 570~800 px/s）。
# 如果在滑动过程中取到车辆坐标，等点击真正发出去时（截图+匹配+adb 往返约 0.4 秒），
# 车已经滑走了一格 —— 结果点到相邻的那辆车。
# 用户实测：本想点 Camaro，结果点开了左边那台 VW XL SPORT（正好是它的左邻居）。
# 所以取坐标前必须先确认画面完全静止。
# 实测帧差（320x180 灰度图的平均像素差）：静止 0.3~0.4，滚动中 46.7 —— 差 100 倍，很好判。
CAR_SETTLE_TOL = 2.0          # 平均帧差小于它就算「这一帧没动」
CAR_SETTLE_CHECKS = 3         # 连续几帧没动才算真的静止
CAR_SETTLE_INTERVAL_S = 0.35  # 每次检查的间隔
CAR_SETTLE_TIMEOUT_S = 25     # 等静止的最长时间
CAR_MATCH_CONFIRM_TOL = 3     # 两帧坐标差 ≤ 这么多像素才算坐标可信

# ---------- 目标车不在当前页时自动翻页找 ----------
CAR_ROW_Y = 460               # 车辆列表第一排的纵坐标（翻页滑动用）
CAR_SCROLL_STEP_PX = 700      # 一次滑动多少像素（约一列宽 718）
CAR_SCROLL_DURATION_MS = 700  # 滑动时长，慢一点免得甩过头
CAR_SCROLL_MAX_STEPS = 3      # 每个方向最多翻几页

# ==================== 模板注册表 ====================
# key 供代码引用；value = (文件名, 用途说明)
# 用 python main.py capture 逐个采集，图片自动保存到 templates/
TEMPLATES = {
    # --- 主界面 ---
    "mode_entry":         ("mode_entry.png",          "主界面『开始』按钮（点它进入选车界面）"),

    # --- 选车界面 ---
    # 用来判断「现在停在游戏哪一屏」（从任意界面接着跑的开关）。
    # 实测：选车界面上 conf 1.00，详情页/主界面上只有 0.37，非常好区分。
    "car_list":           ("car_list.png",            "选车界面标志（左上角『车辆选择』标题）"),

    # --- 模式选择界面 ---
    # 游戏最外层那一屏（经典系列赛 / 试驾挑战 / 对决）。按返回键退到底就是它。
    # 实测：本屏 conf 1.00，其它界面只有 0.29~0.39。
    "mode_card":          ("mode_card.png",           "模式选择界面的『经典系列赛』卡片（识别后点它进该模式）"),

    # --- 车辆详情 ---
    "detail_start":       ("detail_start.png",        "车辆详情『开始』按钮（有油，点它开始匹配）"),
    "detail_skip":        ("detail_skip.png",         "车辆详情『跳过』按钮（没油的标志）"),
    "detail_back":        ("detail_back.png",         "车辆详情『返回』按钮"),

    # --- 匹配 ---
    "match_error":        ("match_error.png",         "匹配时连不上服务器的错误弹窗（识别后点右上角×关闭）"),

    # --- 闪退恢复 ---
    # 说明：这里曾经有个 login_ok（登陆成功标志）。实际采到的图是模式选择界面
    # 底部的『多人游戏』标签，会在模式选择界面上匹到 0.998 造成误判，已经删掉。
    # 现在不需要它了：重启游戏后改成用「界面识别」判断加载是否完成
    # （认出任何一个已知界面就算加载完了，见 bot.py 的 detect_screen）。

    # --- 赛后 ---
    "continue1":          ("continue1.png",           "第一个『继续』按钮（比赛结束后出现）"),
    "continue2":          ("continue2.png",           "第二个『继续』按钮（点完第一个后出现）"),
    "missed_opportunity": ("missed_opportunity.png",  "『错失机会』按钮/文案"),

    # --- 动态奖励 ---
    # 只框左上角『动态奖励』标题。别把卡片框进去：卡面每次都换。
    # 实测两种变体（赛后那种 / 活动那种）上都是 conf 1.00。
    "dynamic_reward":     ("dynamic_reward.png",      "『动态奖励』界面标志（左上角标题）"),

    # --- 里程碑奖励 ---
    "milestone":          ("milestone.png",           "里程碑奖励弹窗标志"),
    "milestone_continue": ("milestone_continue.png",  "里程碑奖励弹窗的『继续』按钮"),

    # --- 段位变更（升段/降段弹窗不同，需分别采集） ---
    "rank_up":            ("rank_up.png",             "升段弹窗标志"),
    "rank_up_continue":   ("rank_up_continue.png",    "升段弹窗的确认按钮"),
    "rank_down":          ("rank_down.png",           "降段弹窗标志"),
    "rank_down_continue": ("rank_down_continue.png",  "降段弹窗的确认按钮"),
}

# 必采模板：缺少这些，脚本无法正常工作
REQUIRED_TEMPLATES = [
    # 界面标志：「从任意界面接着跑」靠它们判断现在停在哪一屏
    "car_list", "mode_card", "dynamic_reward",
    "mode_entry", "detail_start", "detail_skip", "detail_back",
    "continue1", "continue2", "missed_opportunity",
    "milestone", "milestone_continue",
    "rank_up", "rank_up_continue", "rank_down", "rank_down_continue",
]

# ==================== 主界面入口导航序列 ====================
# 从"主界面"进入"选车界面"需要依次点击的东西，按顺序执行。
# 每一项： {"template": "逻辑名"}  或  {"coord": [x, y]}
# 默认：直接点主界面『开始』。
# 若主界面需先点某个模式卡、再点开始，可改成：
#   [{"template": "某个模式"}, {"template": "mode_entry"}]
ENTRY_SEQUENCE = [
    {"template": "mode_entry"},
]

# ==================== 打赏作者 ====================
# 控制台左下角「❤ 打赏作者 ❤」弹窗里显示的收款码。
# 把你的收款码图片放到这里（相对项目根目录），比如 assets/donate.png。
# 界面上没有"更换图片"的入口，直接替换这个文件即可（改路径就改这一行）。
# 没有这张图时弹窗会显示一句提示，不影响其它功能。
DONATE_QR = "assets/donate.png"

# ==================== 动态奖励（选奖励界面） ====================
# 点完『错失机会』（或其它活动入口）会弹出「动态奖励」：从一组卡片里挑一个奖励。
# 每次卡片图案都不一样，所以：
#   · 识别只看左上角『动态奖励』标题（不含任何卡面图案，换奖励照样认）
#   · 选第 N 张 = 点第 N 个卡位（卡位坐标固定，跟画的是什么车无关）
#
# 实测有两种变体，几何不一样，下面这组坐标是两者的「交集」（都能点中）：
#   赛后那种：顶栏可见、底部有『确认』按钮，卡片纵向 457~858，中心 y=657
#   活动那种：全屏遮罩、只有右上角 ×，卡片纵向 423~707，中心 y=565
REWARD_MODE = "auto"          # auto = 自动选第 N 张；manual = 弹窗提醒你自己选
REWARD_PICK_INDEX = 1         # 自动模式选第几张（从 1 开始）
REWARD_MAX_INDEX = 5          # 第 6 张在屏幕外，点不到，所以最多 5
REWARD_CARD_X0 = 227          # 第 1 个卡位的中心 X
REWARD_CARD_STEP = 346        # 卡位间距
REWARD_CARD_Y = 580           # 卡位中心 Y（取两种变体的交集，两种都能点中）
REWARD_CONFIRM_XY = (959, 907)  # 『确认』按钮；没有这个按钮的变体上，点的是空白，无副作用
REWARD_PICK_WAIT_S = 2.0      # 点完卡片等多久，再检查界面关掉了没
REWARD_MANUAL_TIMEOUT_S = 180 # 手动模式等你多久（等超时就先继续跑）
REWARD_POLL_S = 1.0           # 手动模式下检查界面有没有关掉的间隔

# ==================== 循环 ====================
MAX_LOOPS = 0   # 0 = 无限循环；>0 = 刷满 N 场后自动停止

# ==================== 用户设置覆盖（由前端写入 settings.json） ====================
import json as _json


def _load_settings():
    _p = os.path.join(BASE_DIR, "settings.json")
    if not os.path.exists(_p):
        return
    try:
        with open(_p, "r", encoding="utf-8") as _f:
            _ov = _json.load(_f)
        if isinstance(_ov, dict):
            for _k, _v in _ov.items():
                globals()[_k] = _v
    except Exception:
        pass


def reload_settings():
    """重新读取 settings.json 并覆盖到本模块（前端保存后调用）。"""
    _load_settings()


_load_settings()
