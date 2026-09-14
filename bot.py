# -*- coding: utf-8 -*-
"""
bot.py —— 游戏自动化主流程（状态机）

流程：
  主界面(点"开始") → 选车 → 车辆详情(开始/跳过判断) → 匹配 → 比赛(自动驾驶+双击氮气)
  → 赛后(继续/继续/错失机会) → 处理里程碑/升段/降段弹窗 → 回到主界面 → 循环

闪退检测：通过前台包名判断，一旦游戏不在前台即视为闪退，重启游戏并重新导航。
"""
import os
import time

import cv2
import numpy as np

import config
from util import log, ensure_dirs
from adb_helper import ADB, ADBError
from vision import Vision
from version import VERSION_TEXT


class GameCrashed(Exception):
    pass


class BotStopped(Exception):
    """收到外部停止指令。"""
    pass


# ==================== 界面状态（从哪儿接着跑） ====================
# 启动时先看一眼现在停在游戏哪一屏，从那一屏接着往下跑，
# 所以手动点到任意一个流程中途都能接上（比赛中的画面认不出来，见 S_UNKNOWN）。
S_MAIN_MENU = "主界面"
S_MODE_SELECT = "模式选择界面"
S_CAR_LIST = "选车界面"
S_CAR_DETAIL = "车辆详情页"
S_POST_RACE = "赛后结算界面"
S_POPUP = "奖励/段位弹窗"
S_REWARD = "动态奖励界面"
S_MATCH_ERR = "匹配错误弹窗"
S_LOGIN = "登陆成功画面"
S_UNKNOWN = "未知界面（多半在比赛中或加载中）"


def reward_card_xy(index):
    """第 index 张动态奖励卡片该点哪（1 起）。

    卡片图案每次都换，但卡位是固定的，所以直接按位置点。
    实测有两种变体（赛后那种 / 活动那种），卡位横向差 65px、纵向差 92px；
    config 里存的 X0/STEP/Y 是两者的交集，两种都能点中
    （tests/test_bot.py 里用实测数据盯着这件事）。
    """
    top = max(1, int(getattr(config, "REWARD_MAX_INDEX", 5)))
    i = min(max(1, int(index)), top)
    x = int(round(config.REWARD_CARD_X0 + (i - 1) * config.REWARD_CARD_STEP))
    return (x, int(config.REWARD_CARD_Y))


class GameBot:
    def __init__(self):
        ensure_dirs()
        self.adb = ADB()
        self.vis = Vision()
        self.stop = False
        self.loop_count = 0
        self.car_index = 0
        # 图形界面可以给这个回调赋值：出现「动态奖励」时用来弹窗提醒用户自己选。
        # 调用方式 reward_notify(True) 弹窗、reward_notify(False) 关窗。
        self.reward_notify = None

    # ================= 基础 =================
    def grab(self):
        """截图，返回 (bgr, gray)。"""
        if self.stop:
            raise BotStopped()
        data = self.adb.screencap_bytes()
        bgr = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
        if bgr is None:
            raise ADBError("截图解析失败")
        if config.SAVE_DEBUG_SHOTS:
            ts = int(time.time() * 1000)
            cv2.imwrite(os.path.join(config.SHOT_DIR, f"dbg_{ts}.png"), bgr)
        gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
        return bgr, gray

    def find(self, key, gray=None):
        if gray is None:
            _, gray = self.grab()
        return self.vis.find(key, gray)

    def has(self, key, gray=None):
        return self.find(key, gray) is not None

    def click_template(self, key, timeout=15, threshold=None):
        """轮询等待模板出现并点击，成功返回 (x,y)，超时返回 None。"""
        deadline = time.time() + timeout
        while time.time() < deadline:
            _, gray = self.grab()
            pos = self.vis.find(key, gray, threshold)
            if pos:
                x, y, conf = pos
                self.adb.tap(x, y)
                log("点击 [%s] @ (%d,%d) conf=%.2f", key, x, y, conf)
                return (x, y)
            time.sleep(config.POLL_INTERVAL_S)
        log("超时未找到 [%s]", key)
        return None

    def click_xy(self, x, y):
        self.adb.tap(x, y)
        log("点击坐标 (%d,%d)", x, y)

    def wait_for(self, key, timeout):
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.has(key):
                return True
            time.sleep(config.POLL_INTERVAL_S)
        return False

    # ================= 闪退检测 =================
    def foreground_is_game(self):
        pkg = self.adb.foreground_package()
        if pkg is None:          # 拿不到信息时不过度反应
            return True
        return pkg == config.GAME_PACKAGE

    def game_alive(self):
        """游戏进程是否还在（比只看前台更可靠）。"""
        try:
            rc, out = self.adb._run_raw("shell", "pidof", config.GAME_PACKAGE)
        except ADBError:
            return True
        if rc != 0:
            return False
        return bool(out.strip())

    def game_gone(self):
        """游戏是不是已经没了：不在前台，或者进程已经不存在。"""
        if not self.foreground_is_game():
            return True
        return not self.game_alive()

    def kill_game(self, timeout=20):
        """强停游戏，并等到进程真正消失再返回。"""
        try:
            self.adb.force_stop()
        except ADBError:
            pass
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.stop:
                raise BotStopped()
            if not self.game_alive():
                return True
            time.sleep(config.POLL_INTERVAL_S)
        log("  警告：游戏进程仍未退出，仍继续尝试启动")
        return False

    def check_crash(self):
        if self.stop:
            raise BotStopped()
        if not self.foreground_is_game():
            raise GameCrashed()

    def relaunch_game(self):
        """闪退恢复：最多连续重启若干次（加载中再次闪退会自动重来）。"""
        max_attempts = config.RELAUNCH_MAX_ATTEMPTS
        for attempt in range(1, max_attempts + 1):
            log("闪退恢复：第 %d/%d 次重启 ...", attempt, max_attempts)
            if self._relaunch_once():
                log("重启成功，已回到主界面")
                return True
            log("第 %d 次重启未成功", attempt)
            time.sleep(8)
        log("连续 %d 次重启均未成功", max_attempts)
        return False

    def _relaunch_once(self):
        """一次完整重启：强停 → 启动 → 等进前台 → 等登陆成功 → 点坐标 → 等主界面。
        全程反复检测游戏是否还在（前台包名 + 进程存在 双保险），
        一旦闪退立即返回 False，由上层马上重来。"""
        self.kill_game()
        time.sleep(3)
        self.adb.start_app()

        # 1) 先等游戏进入前台（刚启动时可能还停在桌面，不能立刻当成闪退）
        fg_deadline = time.time() + config.RELAUNCH_FOREGROUND_WAIT_S
        while time.time() < fg_deadline:
            if self.stop:
                raise BotStopped()
            if self.foreground_is_game():
                break
            time.sleep(config.POLL_INTERVAL_S)
        else:
            log("  游戏未进入前台，这次重启作废")
            return False
        log("  游戏已进入前台，等它加载 ...")

        # 2) 静默等待：这段时间【绝不截图】
        #    原因：screencap 要在模拟器里做 PNG 编码，非常吃 CPU；
        #    游戏加载时 CPU 已经很满，再截图会直接把游戏压崩（实测每次约 43 秒必崩）。
        #    静默期只查「前台包名 + 进程是否还在」，这两个操作很轻，实测安全。
        log("  静默等待 %d 秒（期间不截图，避免把游戏压崩）...", config.RELAUNCH_QUIET_S)
        quiet_until = time.time() + config.RELAUNCH_QUIET_S
        while time.time() < quiet_until:
            if self.game_gone():
                log("  加载过程中游戏闪退了")
                return False
            time.sleep(2)

        # 3) 静默期结束，加载基本完成，用「界面识别」等它变成任何认得出的界面。
        #    不再依赖登陆成功标志（那个模板采错了），认得出界面就说明加载完了，
        #    回到主界面/模式选择由 run_once 的界面识别继续处理。
        log("  等待游戏加载完成（最多 %d 秒）...", config.RELAUNCH_LOAD_TIMEOUT_S)
        deadline = time.time() + config.RELAUNCH_LOAD_TIMEOUT_S
        interval = max(config.POLL_INTERVAL_S, 4.0)   # 加载期间截图要稀疏，免得压崩游戏
        taps = 0
        last_tap = time.time()
        state = None
        while time.time() < deadline:
            if self.stop:
                raise BotStopped()
            if self.game_gone():
                log("  加载过程中游戏闪退了")
                return False
            state = self.detect_screen()
            if state != S_UNKNOWN:
                log("  游戏已加载完成，当前界面：%s", state)
                return True
            # 一直认不出 → 可能是「登陆成功/点击继续」那种要手动点一下的画面
            if taps < 3 and time.time() - last_tap > 20:
                taps += 1
                last_tap = time.time()
                self.adb.tap(*config.RELAUNCH_TAP)
                log("  认不出界面，试点一下 (%d,%d) 回主界面（第 %d 次）",
                    config.RELAUNCH_TAP[0], config.RELAUNCH_TAP[1], taps)
            time.sleep(interval)
        log("  等不到认得出的界面（最后状态：%s）", state)
        return False

    # ================= 导航 =================
    def navigate_to_mode(self):
        """从主界面进入选车界面（按 ENTRY_SEQUENCE 依次点击）。"""
        if not self.wait_for("mode_entry", timeout=8):
            log("未检测到主界面『开始』（可能已在其它界面），仍尝试执行入口序列")
        for step in config.ENTRY_SEQUENCE:
            if step.get("template"):
                self.click_template(step["template"], timeout=20)
            elif step.get("coord"):
                self.click_xy(*step["coord"])
            time.sleep(2.5)
        # 点完主界面『开始』即进入选车界面（无需图片判断）
        time.sleep(2)

    # ================= 选车 =================
    def wait_screen_stable(self, timeout=None, checks=None, interval=None, tol=None):
        """等选车界面完全静止再取坐标。

        实测：进入选车界面后，车辆列表会横向滑动好几秒（约 570~800 px/s）。
        如果在滑动途中取到车辆坐标，等点击真正发出去时车已经滑走一格，
        结果点到相邻的那辆车（用户实测：想点 Camaro，点开了左边的 VW XL SPORT）。
        实测平均帧差：静止 0.3~0.4，滚动中 46.7，所以很好判。
        """
        timeout = timeout if timeout is not None else config.CAR_SETTLE_TIMEOUT_S
        checks = checks if checks is not None else config.CAR_SETTLE_CHECKS
        interval = interval if interval is not None else config.CAR_SETTLE_INTERVAL_S
        tol = tol if tol is not None else config.CAR_SETTLE_TOL

        prev = None
        stable = 0
        deadline = time.time() + timeout
        while time.time() < deadline:
            self.check_crash()
            bgr, _ = self.grab()
            small = cv2.resize(cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY), (320, 180))
            if prev is not None:
                diff = float(np.mean(cv2.absdiff(small, prev)))
                if diff <= tol:
                    stable += 1
                    if stable >= checks:
                        log("选车界面已静止（连续 %d 帧无变化）", checks)
                        return True
                else:
                    stable = 0
            prev = small
            time.sleep(interval)
        log("等选车界面静止超时（%ds），仍继续", timeout)
        return False

    def match_car(self, name, gray):
        """按车辆模板匹配，返回 (x, y, conf) 或 None。"""
        return self.vis.find_file(name + ".png", gray,
                                  threshold=config.CAR_MATCH_THRESHOLD,
                                  min_margin=config.CAR_MATCH_MIN_MARGIN)

    def match_car_settled(self, name, tries=6):
        """连拍两帧、坐标一致才认，避免拿到「正在滑动」的过期坐标。"""
        prev = None
        for _ in range(tries):
            _, gray = self.grab()
            pos = self.match_car(name, gray)
            if pos is None:
                return None
            if (prev is not None
                    and abs(pos[0] - prev[0]) <= config.CAR_MATCH_CONFIRM_TOL
                    and abs(pos[1] - prev[1]) <= config.CAR_MATCH_CONFIRM_TOL):
                log("车辆 [%s] 坐标已确认稳定 @ (%d,%d) conf=%.3f",
                    name, pos[0], pos[1], pos[2])
                return pos
            prev = pos
            time.sleep(config.CAR_SETTLE_INTERVAL_S)
        log("车辆 [%s] 坐标一直在变（画面还在动），这次不用它", name)
        return None

    def scroll_car_list(self, direction):
        """翻一页车辆列表。direction=-1 看列表前面的车，+1 看后面的车。"""
        y = config.CAR_ROW_Y
        step = config.CAR_SCROLL_STEP_PX
        x0 = 400
        if direction > 0:      # 看后面的车 → 手指往左拖
            x1, x2 = x0 + step, x0
        else:                  # 看前面的车 → 手指往右拖
            x1, x2 = x0, x0 + step
        try:
            self.adb.swipe(x1, y, x2, y, config.CAR_SCROLL_DURATION_MS)
        except ADBError as e:
            log("翻页滑动失败: %s", e)
            return False
        log("翻页找车（%s）", "往列表后面" if direction > 0 else "往列表前面")
        self.wait_screen_stable()
        return True

    def open_car_detail(self, name, pos):
        """点开车辆卡片；成功进入详情页返回该页灰度图，没进去返回 None。"""
        log("点击车辆 [%s] @ (%d,%d) conf=%.3f", name, pos[0], pos[1], pos[2])
        self.click_xy(pos[0], pos[1])
        time.sleep(2.5)
        _, gray = self.grab()
        # 详情页才有『开始』/『跳过』，用它们判断有没有真的点开
        if self.vis.has("detail_start", gray, threshold=0.45) or \
                self.vis.has("detail_skip", gray, threshold=0.45):
            return gray
        log("点了 [%s] 但没进车辆详情页（画面可能又动了）", name)
        return None

    def judge_detail(self, name, gray):
        """判断详情页有没有油。返回 True=已点『开始』去匹配。"""
        start_p = self.vis.find("detail_start", gray, threshold=0.45)
        skip_p = self.vis.find("detail_skip", gray, threshold=0.45)
        sc = start_p[2] if start_p else 0.0
        kc = skip_p[2] if skip_p else 0.0
        log("详情判断: 开始=%.2f  跳过=%.2f", sc, kc)
        # 「开始」优先且更可信 → 有油
        if sc >= config.MATCH_THRESHOLD and sc >= kc:
            log("车辆 [%s] 有油，点击『开始』进入匹配", name)
            self.click_template("detail_start", timeout=10)
            return True
        if kc >= config.MATCH_THRESHOLD:
            log("车辆 [%s] 没油（检测到『跳过』），返回换下一辆", name)
        else:
            log("车辆 [%s] 详情页没识别到开始/跳过，返回换下一辆", name)
        # 退回列表：否则脚本会停在详情页上继续找车，越找越乱
        self.click_template("detail_back", timeout=5)
        time.sleep(2)
        self.wait_screen_stable()      # 返回后列表可能又滑一下
        return False

    def search_cars_by_scrolling(self, order):
        """当前页找不到车时，前后翻页找。"""
        max_steps = max(1, getattr(config, "CAR_SCROLL_MAX_STEPS", 3))
        for direction in (-1, 1):
            moved = 0
            for _ in range(max_steps):
                if not self.scroll_car_list(direction):
                    break
                moved += 1
                for name in order:
                    pos = self.match_car_settled(name)
                    if pos is None:
                        continue
                    log("翻页后找到车辆 [%s]", name)
                    gray = self.open_car_detail(name, pos)
                    if gray is None:
                        self.wait_screen_stable()
                        continue
                    if self.judge_detail(name, gray):
                        return True
            for _ in range(moved):     # 翻回原来的位置
                self.scroll_car_list(-direction)
        return False

    def select_car_and_match(self):
        """按车辆图片识别选车：找到车→点击→详情判断(开始/跳过)→有油则开始匹配。"""
        if not config.CAR_TEMPLATES:
            log("未配置车辆模板（config.CAR_TEMPLATES 为空）")
            return False
        n = len(config.CAR_TEMPLATES)
        # 轮转顺序：优先用上次轮到的那辆
        order = [config.CAR_TEMPLATES[(self.car_index + i) % n] for i in range(n)]
        self.car_index += n

        # 关键：先等列表停止滚动，再取坐标（否则会点到相邻的车）
        self.wait_screen_stable()

        for name in order:
            self.check_crash()
            pos = self.match_car_settled(name)
            if pos is None:
                log("本页没有车辆 [%s]", name)
                continue
            gray = self.open_car_detail(name, pos)
            if gray is None:
                self.wait_screen_stable()
                continue
            if self.judge_detail(name, gray):
                return True

        log("本页没有配置的车辆，尝试翻页 ...")
        if self.search_cars_by_scrolling(order):
            return True

        log("选车失败：当前页和前后 %d 页都没找到配置的车辆",
            getattr(config, "CAR_SCROLL_MAX_STEPS", 3))
        return False

    # ================= 比赛 =================
    def play_race(self):
        """返回 True 表示真的开始比赛了（打完/超时都算）；False 表示没匹配上，本场作废。"""
        if not self._wait_match_start():
            return False
        self._race_loop()
        return True

    def _wait_match_start(self):
        """等待匹配完成。返回 False 表示匹配一直失败、本场没跑起来。"""
        err_tpl = self.vis.template_exists("match_error")
        max_retry = max(1, getattr(config, "MATCH_ERROR_MAX_RETRIES", 5))
        log("已点开始匹配，等待 %d 秒%s ...", config.MATCHING_DELAY_S,
            "（同时检测匹配错误弹窗）" if err_tpl else "（不做图片判断）")
        deadline = time.time() + config.MATCHING_DELAY_S
        last_check = 0.0
        retry = 0
        while time.time() < deadline:
            self.check_crash()
            # 匹配时游戏在加载赛道，截图不能太频繁，否则容易把游戏压崩
            if err_tpl and (time.time() - last_check) >= config.MATCH_ERROR_CHECK_S:
                last_check = time.time()
                pos = self.find("match_error")
                if pos:
                    retry += 1
                    if retry > max_retry:
                        log("匹配连续失败 %d 次，本场放弃", max_retry)
                        return False
                    log("第 %d/%d 次匹配失败，重新发起 ...", retry, max_retry)
                    self.close_match_error(pos)
                    if not self.retry_match():
                        log("重新发起匹配没成功，本场放弃")
                        return False
                    deadline = time.time() + config.MATCHING_DELAY_S
                    continue
            time.sleep(config.POLL_INTERVAL_S)
        log("匹配等待结束，进入比赛阶段")
        return True

    def retry_match(self):
        """匹配失败后重新发起匹配。

        实测（日志 + 用户反馈）：匹配失败时游戏会把你【退回选车界面】，
        那里没有详情页的『开始』按钮 —— 旧代码直接找『开始』必然失败，
        然后就白等一轮进"比赛"，实际上根本没匹配上。

        所以这里先看一屏再决定怎么走：
          · 还在车辆详情页 → 直接点『开始』
          · 已被退回选车界面 → 重新选一次车（选车流程内部会点『开始』）
        """
        state = self.detect_screen()
        log("重新发起匹配：当前界面是「%s」", state)

        if state == S_CAR_DETAIL:
            if self.click_template("detail_start", timeout=10):
                log("还在详情页，已重新点『开始』")
                return True
            log("详情页上没点到『开始』")
            return False

        if state == S_CAR_LIST:
            log("已被退回选车界面，重新选车再匹配（这是匹配失败后的正常走向）")
            return self.select_car_and_match()

        # 弹窗可能还没散尽之类：等一下再看一眼
        time.sleep(2)
        state = self.detect_screen()
        log("再看一眼：当前界面是「%s」", state)
        if state == S_CAR_DETAIL:
            return bool(self.click_template("detail_start", timeout=10))
        if state == S_CAR_LIST:
            log("已被退回选车界面，重新选车再匹配")
            return self.select_car_and_match()
        log("界面认不出来（%s），不硬点，本场放弃", state)
        return False

    def _race_loop(self):
        log("比赛进行中：自动驾驶 + 每 %d 秒双击氮气", config.NITRO_INTERVAL_S)
        start = time.time()
        last_nitro = start
        quiet_until = start + config.RACE_START_QUIET_S
        while time.time() - start < config.RACE_TIMEOUT_S:
            self.check_crash()
            now = time.time()
            if now - last_nitro >= config.NITRO_INTERVAL_S:
                self.adb.double_tap(config.NITRO_X, config.NITRO_Y)
                log("双击氮气 @ (%d,%d)", config.NITRO_X, config.NITRO_Y)
                last_nitro = now
            # 赛道加载那几秒不截图，避免把游戏压崩
            if time.time() >= quiet_until and self.has("continue1"):
                log("检测到第一个『继续』，比赛结束")
                return
            time.sleep(config.POLL_INTERVAL_S)
        log("比赛超时（>%ds），继续后续流程", config.RACE_TIMEOUT_S)

    # ================= 赛后 =================
    def post_race(self):
        """赛后结算：按『继续1 → 继续2 → 错失机会』依次点掉。

        做成「看到哪个点哪个」而不是固定顺序，这样从中间任何一步接着跑都行
        （比如你手动已经点过一次『继续』，脚本停在第 2 个上也能接）。
        """
        log("赛后结算：点『继续1』→ 点『继续2』→ 点『错失机会』")
        keys = ("continue1", "continue2", "missed_opportunity")
        deadline = time.time() + config.POST_RACE_TIMEOUT_S
        missing = 0
        while time.time() < deadline:
            self.check_crash()
            _, gray = self.grab()
            hit = None
            for k in keys:
                if self.vis.template_exists(k) and self.vis.has(k, gray):
                    hit = k
                    break
            if hit is None:
                missing += 1
                if missing >= 2:      # 连续两次都没看到 → 结算界面走完了
                    break
                time.sleep(1.5)
                continue
            missing = 0
            self.click_template(hit, timeout=5)
            time.sleep(2.5)
        self.settle_popups()

    def settle_popups(self):
        """处理赛后弹窗（里程碑 / 升段 / 降段），直到确认回到主界面。

        注意：赛后切回主界面时，主界面会【先】渲染出来，里程碑/段位弹窗是稍后
        才加载的。如果一看到主界面就退出，弹窗就被漏掉了（用户实测遇到）。
        所以要连续确认若干次都没有弹窗，才算真的结束。
        """
        log("处理赛后弹窗 ...")
        need = max(1, getattr(config, "POST_RACE_STABLE_CHECKS", 3))
        gap = getattr(config, "POST_RACE_STABLE_INTERVAL_S", 2)
        deadline = time.time() + config.POST_RACE_TIMEOUT_S
        stable = 0
        while time.time() < deadline:
            self.check_crash()
            _, gray = self.grab()

            # 弹窗优先：只要还在就处理，并把确认计数清零
            if self.vis.template_exists("dynamic_reward") and self.vis.has("dynamic_reward", gray):
                # 点完『错失机会』后最常见的就是这个，不处理会一直空等到超时
                log("出现『动态奖励』界面")
                stable = 0
                self.handle_reward()
                continue
            if self.vis.has("milestone", gray):
                log("出现里程碑奖励弹窗")
                stable = 0
                if self.click_template("milestone_continue", timeout=10):
                    time.sleep(1.5)
                continue
            if self.vis.has("rank_up", gray):
                log("出现【升段】通知")
                stable = 0
                if self.click_template("rank_up_continue", timeout=10):
                    time.sleep(1.5)
                continue
            if self.vis.has("rank_down", gray):
                log("出现【降段】通知")
                stable = 0
                if self.click_template("rank_down_continue", timeout=10):
                    time.sleep(1.5)
                continue

            # 没有弹窗：若在主界面就累计"干净"次数，够了才收工
            if self.vis.has("mode_entry", gray):
                stable += 1
                if stable >= need:
                    log("已确认回到主界面（连续 %d 次无弹窗）", stable)
                    return
                log("疑似回到主界面，再等 %d 秒看弹窗会不会弹出来（%d/%d）",
                    gap, stable, need)
                time.sleep(gap)
                continue

            stable = 0
            time.sleep(config.POLL_INTERVAL_S)
        log("赛后弹窗处理超时，尝试重新导航")
        self.navigate_to_mode()

    # ================= 动态奖励 =================
    def reward_closed(self):
        """动态奖励界面关掉了没。"""
        return not self.has("dynamic_reward")

    def notify_reward(self, show):
        """通知图形界面弹/关提醒窗（命令行下没有回调，就只写日志）。"""
        cb = getattr(self, "reward_notify", None)
        if cb is None:
            return
        try:
            cb(show)
        except Exception as e:
            log("奖励提醒弹窗出错：%s", e)

    def handle_reward(self):
        """处理「动态奖励」界面。

        auto   → 自动点第 N 张卡片（有的变体还要再点一下『确认』）
        manual → 弹个提醒窗，等你手动选完（界面关掉）再继续
        """
        mode = str(getattr(config, "REWARD_MODE", "auto") or "auto").lower()
        if mode == "manual":
            return self.handle_reward_manual()
        return self.handle_reward_auto()

    def handle_reward_auto(self):
        idx = int(getattr(config, "REWARD_PICK_INDEX", 1))
        top = int(getattr(config, "REWARD_MAX_INDEX", 5))
        if idx > top:
            log("配置的自动选第 %d 张超出范围（第 %d 张在屏幕外），按第 %d 张处理",
                idx, top + 1, top)
            idx = top
        x, y = reward_card_xy(idx)
        log("动态奖励：自动选第 %d 张 @ (%d,%d)", idx, x, y)
        self.click_xy(x, y)
        time.sleep(config.REWARD_PICK_WAIT_S)
        if self.reward_closed():
            log("奖励已选择（界面已关闭）")
            return True
        # 还开着 → 说明这个变体需要再点一下『确认』
        cx, cy = config.REWARD_CONFIRM_XY
        log("界面还在，点『确认』@ (%d,%d)", cx, cy)
        self.click_xy(cx, cy)
        time.sleep(config.REWARD_PICK_WAIT_S)
        if self.reward_closed():
            log("奖励已选择")
            return True
        log("点了但界面没关（可能这次变体不同），留给下一轮再处理")
        return False

    def handle_reward_manual(self):
        """手动模式：弹窗提醒你自己去选，脚本在旁边等。"""
        log("动态奖励：手动模式 —— 请自己去游戏里挑一个奖励")
        self.notify_reward(True)
        try:
            deadline = time.time() + config.REWARD_MANUAL_TIMEOUT_S
            while time.time() < deadline:
                self.check_crash()
                if self.reward_closed():
                    log("奖励界面已关闭（你已经选好了），继续跑")
                    return True
                time.sleep(config.REWARD_POLL_S)
            log("等了 %d 秒还没选完，先继续跑", config.REWARD_MANUAL_TIMEOUT_S)
            return False
        finally:
            self.notify_reward(False)

    # ================= 界面识别（从哪一屏接着跑） =================
    def detect_screen(self, gray=None):
        """看现在停在游戏哪一屏。返回上面那组 S_ 状态之一。

        判断顺序有讲究：弹窗是盖在别的界面上的，所以先认弹窗；
        「主界面」和「车辆详情页」靠各自的按钮区分（实测互不干扰）：
            mode_entry   在选车界面/详情页只有 0.34/0.37，主界面 0.98
            detail_start 在主界面/选车界面只有 0.37/0.40，详情页 1.00
        """
        if gray is None:
            _, gray = self.grab()

        # 1) 弹窗类优先
        if self.vis.template_exists("match_error") and self.vis.has("match_error", gray):
            return S_MATCH_ERR
        for key in ("milestone", "rank_up", "rank_down"):
            if self.vis.template_exists(key) and self.vis.has(key, gray):
                return S_POPUP
        for key in ("continue1", "continue2", "missed_opportunity"):
            if self.vis.template_exists(key) and self.vis.has(key, gray):
                return S_POST_RACE

        # 动态奖励是整屏覆盖的，要排在主界面/选车前面判
        if self.vis.template_exists("dynamic_reward") and self.vis.has("dynamic_reward", gray):
            return S_REWARD

        # 2) 主界面 / 车辆详情页 / 模式选择
        if self.vis.has("mode_entry", gray):
            return S_MAIN_MENU
        if (self.vis.template_exists("detail_start")
                and self.vis.has("detail_start", gray, threshold=0.6)) or \
           (self.vis.template_exists("detail_skip")
                and self.vis.has("detail_skip", gray, threshold=0.6)):
            return S_CAR_DETAIL

        # 3) 选车界面：标题特征，或者能匹到配置的车辆卡片
        if self.vis.template_exists("car_list") and self.vis.has("car_list", gray):
            return S_CAR_LIST
        for name in config.CAR_TEMPLATES:
            if self.match_car(name, gray):
                return S_CAR_LIST

        # 4) 模式选择界面（游戏最外层那一屏）
        if self.vis.template_exists("mode_card") and self.vis.has("mode_card", gray):
            return S_MODE_SELECT

        return S_UNKNOWN

    def wait_for_known_screen(self, timeout=None, interval=5.0):
        """认不出界面时（多半在比赛中或加载中）等它变成认得出的界面。

        这里【不点氮气、不点任何坐标】：认不出界面时无法确认真的在比赛，
        乱点坐标可能点到别的按钮上（比不点更糟）。
        """
        timeout = timeout if timeout is not None else config.RACE_TIMEOUT_S
        deadline = time.time() + timeout
        while time.time() < deadline:
            self.check_crash()
            time.sleep(interval)
            state = self.detect_screen()
            if state != S_UNKNOWN:
                log("界面变成了：%s", state)
                return state
            log("还认不出（可能仍在比赛/加载中），继续等 ...")
        log("等了 %d 秒还是认不出界面", timeout)
        return None

    def close_match_error(self, pos=None):
        """点掉匹配错误弹窗右上角的 ×。返回是否真的点了。

        关掉之后游戏会退到哪一屏不一定（实测是退回选车界面），
        所以「重新发起匹配」交给 retry_match() 判断，这里只管关弹窗。
        """
        if pos is None:
            pos = self.find("match_error")
        if not pos:
            log("没找到匹配错误弹窗")
            return False
        if config.MATCH_ERROR_TAP:
            tx, ty = config.MATCH_ERROR_TAP
        else:
            # 模板是「标题栏 + ×」，× 在模板右上角 → 用偏移算出绝对坐标
            tx = pos[0] + config.MATCH_ERROR_X_OFFSET
            ty = pos[1] + config.MATCH_ERROR_Y_OFFSET
        log("检测到匹配错误弹窗(conf=%.2f)，点右上角 × @ (%d,%d)", pos[2], tx, ty)
        self.click_xy(tx, ty)
        time.sleep(2)
        return True

    def resume_from_detail(self):
        """手动停在车辆详情页时：有油就直接开始，没油就返回列表接着选车。"""
        _, gray = self.grab()
        if self.judge_detail("手动选的那辆车", gray):
            return True
        # judge_detail 里已经点了返回并等画面静止 → 现在应该在选车界面
        return self.select_car_and_match()

    def enter_mode(self):
        """停在模式选择界面时：点『经典系列赛』卡片进该模式。"""
        log("停在模式选择界面 → 点『经典系列赛』卡片进入该模式")
        return self.click_template("mode_card", timeout=15) is not None

    # ================= 单场完整流程 =================
    def run_once(self):
        """先认出现在停在游戏哪一屏，从那一屏接着往下跑。"""
        log("========== 第 %d 场 ==========", self.loop_count + 1)

        state = None
        for _ in range(4):
            state = self.detect_screen()
            log("当前界面：%s", state)
            if state == S_UNKNOWN:
                log("认不出当前界面（多半在比赛中或加载中），等它变成认得出的界面 ...")
                if not self.wait_for_known_screen():
                    log("等太久仍认不出界面，本轮先跳过")
                    return
                continue
            break

        # ---- 已经是后段界面：直接接着走 ----
        if state == S_REWARD:
            log("停在动态奖励界面上 → 先把它处理掉")
            self.handle_reward()
            return
        if state == S_POPUP:
            log("停在奖励/段位弹窗上 → 先把弹窗处理完")
            self.settle_popups()
            return
        if state == S_POST_RACE:
            log("停在赛后结算界面 → 直接接着走赛后流程")
            self.post_race()
            return
        if state == S_MATCH_ERR:
            log("停在匹配错误弹窗上 → 关掉弹窗并重新发起匹配")
            self.close_match_error()
            if not self.retry_match():
                log("没能重新发起匹配，本轮跳过")
                return
            if self.play_race():
                self.post_race()
            return

        # ---- 前段界面：先走到「已经点了开始匹配」 ----
        if state == S_MODE_SELECT:
            log("停在游戏最外层的模式选择界面 → 先进经典系列赛")
            if not self.enter_mode():
                log("点不开模式卡片，跳过本场")
                return
            time.sleep(3)
            state = S_MAIN_MENU

        if state == S_MAIN_MENU:
            self.navigate_to_mode()          # 主界面 → 选车界面
            if not self.select_car_and_match():
                log("本轮选车失败，跳过本场")
                return
        elif state == S_CAR_LIST:
            if not self.select_car_and_match():
                log("本轮选车失败，跳过本场")
                return
        elif state == S_CAR_DETAIL:
            if not self.resume_from_detail():
                log("这辆车没油且没找到有油的车，跳过本场")
                return

        if not self.play_race():      # 匹配 → 比赛(氮气) → 结算
            log("本场没匹配上，作废（不跑赛后流程，直接看下一轮该从哪继续）")
            return
        self.post_race()              # 继续/继续/错失机会 → 处理弹窗
        log("本场流程结束")

    # ================= 游戏包名（自动识别） =================
    def setup_game_package(self):
        """开机自动认游戏包名。

        狂野飙车9 国服分渠道发行（TapTap / 4399 / 华为 / 小米 / 应用宝 …），
        包名各不相同。这里直接问模拟器：装的是哪个，就自动用哪个，
        用户不用改代码。认不出来就保持原配置并给个提示。
        """
        configured = config.GAME_PACKAGE
        try:
            listing = self.adb.list_packages()
        except ADBError as e:
            log("警告：读不到已安装应用列表（%s），沿用配置的包名 %s", e, configured)
            return

        if configured and f"package:{configured}" in listing:
            log("游戏包名：%s（配置的，已确认）", configured)
            return

        found = config.guess_game_package(listing)
        if not found:
            log("警告：模拟器里没找到《狂野飙车9》（配置的是 %s）", configured or "(空)")
            log("      确认游戏装在【这个】模拟器里，或者同时开着多个模拟器时选对设备")
            return

        running = [p for p in found if self.adb.pid_of(p)]
        fg = self.adb.foreground_package()
        best = config.pick_game_package(found, configured, foreground=fg, running=running)
        if not best:
            log("警告：没能确定游戏包名，沿用 %s", configured)
            return

        config.GAME_PACKAGE = best
        act = self.adb.resolve_activity(best)
        if act:
            config.GAME_ACTIVITY = act
        log("游戏包名：配置的 %s 没找到，自动改用 %s", configured or "(空)", best)
        if len(found) > 1:
            log("  设备上共有 %d 个候选：%s", len(found), "、".join(found))
        if act:
            log("  启动 Activity：%s", act)
        log("  （想固定下来的话，改 config.py 的 GAME_PACKAGE / GAME_ACTIVITY）")

    # ================= 主循环 =================
    def run(self):
        # 每次启动都重新加载 config.py。
        # 否则程序里一直是打开时那份旧配置：往 config.py 加了新参数后，
        # 只要不重启整个程序就会报 "module 'config' has no attribute ..."。
        try:
            import importlib
            importlib.reload(config)
            log("已重新加载 config.py")
        except Exception as e:
            log("重新加载 config 失败: %s", e)
        log("A9 自动驾驶台 %s 启动", VERSION_TEXT)
        self.setup_game_package()      # 自动认游戏包名（渠道服也能直接用）
        log("开始运行（Ctrl+C 停止）")
        if not self.foreground_is_game():
            log("游戏未在前台，先启动 ...")
            self.relaunch_game()
        # 不预设起点：run_once 会先认出现在停在哪一屏，从那一屏接着跑
        while not self.stop:
            try:
                self.run_once()
            except GameCrashed:
                log("检测到游戏闪退！")
                # 一直尝试恢复到主界面为止（加载界面可能再次闪退）
                try:
                    while not self.stop and not self.relaunch_game():
                        log("重启未成功，15 秒后再次尝试 ...")
                        time.sleep(15)
                except BotStopped:
                    log("收到停止指令，已停止")
                    break
                if self.stop:
                    break
                log("已重新进入游戏，继续下一场")
                continue
            except ADBError as e:
                log("ADB 错误：%s", e)
                time.sleep(3)
            except KeyboardInterrupt:
                log("手动停止")
                break
            except BotStopped:
                log("收到停止指令，已停止")
                break
            self.loop_count += 1
            if config.MAX_LOOPS > 0 and self.loop_count >= config.MAX_LOOPS:
                log("已刷满 %d 场，停止", config.MAX_LOOPS)
                break
