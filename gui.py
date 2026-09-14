# -*- coding: utf-8 -*-
"""
gui.py —— A9 自动驾驶台（桌面客户端界面）

· 高 DPI 感知：在 150% 缩放的屏幕上依然清晰锐利（不再被系统拉伸模糊）
· 客户端布局：左侧导航栏 + 卡片式内容区（状态 / 参数 / 日志 / 模板）
"""
import base64
import ctypes
import os
import shutil
import threading
import tkinter as tk
from tkinter import filedialog, messagebox

import config
from util import log, get_logs_since, ensure_dirs
from settings_io import SETTINGS_SCHEMA, current_settings, save_settings
from version import VERSION_TEXT


# ==================== 高 DPI ====================
def _enable_dpi_awareness():
    """必须在创建 Tk 窗口之前调用，否则画面会被系统拉伸而模糊。"""
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)      # Per-Monitor V2
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def _screen_dpi():
    try:
        hdc = ctypes.windll.user32.GetDC(0)
        dpi = ctypes.windll.gdi32.GetDeviceCaps(hdc, 88)    # LOGPIXELSX
        ctypes.windll.user32.ReleaseDC(0, hdc)
        return dpi or 96
    except Exception:
        return 96


_enable_dpi_awareness()
DPI = _screen_dpi()
S = DPI / 96.0


def px(n):
    return int(round(n * S))


# ==================== 配色 ====================
BG       = "#0a0d14"
SIDEBAR  = "#0d111a"
CARD     = "#141924"
CARD2    = "#1a2130"
HOVER    = "#202a3d"
BORDER   = "#232b3c"
TEXT     = "#e9eef8"
SUB      = "#8b96ad"
ACCENT   = "#22d3ee"
ACCENT_H = "#67e8f9"
VIOLET   = "#8b5cf6"
OK       = "#34d399"
WARN     = "#fbbf24"
DANGER   = "#f87171"
DANGER_H = "#fca5a5"

FONT_UI = "Microsoft YaHei UI"
FONT_MONO = "Consolas"


def f_ui(size, bold=False):
    return (FONT_UI, size, "bold") if bold else (FONT_UI, size)


def f_mono(size, bold=False):
    return (FONT_MONO, size, "bold") if bold else (FONT_MONO, size)


def round_rect(cv, x1, y1, x2, y2, r, **kw):
    """在 Canvas 上画圆角矩形（smooth 折线近似）。"""
    pts = [
        x1 + r, y1, x1 + r, y1, x2 - r, y1, x2 - r, y1,
        x2, y1, x2, y1 + r, x2, y1 + r, x2, y2 - r,
        x2, y2 - r, x2, y2, x2 - r, y2, x2 - r, y2,
        x1 + r, y2, x1 + r, y2, x1, y2, x1, y2 - r,
        x1, y2 - r, x1, y1 + r, x1, y1 + r, x1, y1,
    ]
    return cv.create_polygon(pts, smooth=True, **kw)


class RoundButton(tk.Canvas):
    """圆角按钮（Canvas 绘制，支持悬停/禁用）。"""

    def __init__(self, parent, text, command, width, height,
                 bg, hover, fg, font=None, parent_bg=BG):
        super().__init__(parent, width=width, height=height, bg=parent_bg,
                         highlightthickness=0, bd=0, cursor="hand2")
        self._command = command
        self._bg = bg
        self._hover = hover
        self._enabled = True
        r = min(height // 2, px(12))
        self._shape = round_rect(self, 1, 1, width - 1, height - 1, r, fill=bg, outline="")
        self._label = self.create_text(width // 2, height // 2, text=text,
                                       fill=fg, font=font or f_ui(11, True))
        self.bind("<Button-1>", self._click)
        self.bind("<Enter>", self._enter)
        self.bind("<Leave>", self._leave)

    def _click(self, _e):
        if self._enabled and self._command:
            self._command()

    def _enter(self, _e):
        if self._enabled:
            self.itemconfigure(self._shape, fill=self._hover)

    def _leave(self, _e):
        if self._enabled:
            self.itemconfigure(self._shape, fill=self._bg)

    def set_enabled(self, on):
        self._enabled = on
        self.configure(cursor="hand2" if on else "arrow")
        self.itemconfigure(self._shape, fill=self._bg if on else CARD2)
        self.itemconfigure(self._label, fill=TEXT if on else SUB)


class NavItem(tk.Frame):
    """侧栏导航项。"""

    def __init__(self, parent, glyph, text, command):
        super().__init__(parent, bg=SIDEBAR, cursor="hand2", height=px(44))
        self.pack_propagate(False)
        self.command = command
        self.active = False

        self.bar = tk.Frame(self, bg=SIDEBAR, width=px(3))
        self.bar.pack(side="left", fill="y")
        self.icon = tk.Label(self, text=glyph, bg=SIDEBAR, fg=SUB, font=f_ui(13))
        self.icon.pack(side="left", padx=(px(18), px(12)))
        self.label = tk.Label(self, text=text, bg=SIDEBAR, fg=SUB, font=f_ui(11))
        self.label.pack(side="left")

        for w in (self, self.bar, self.icon, self.label):
            w.bind("<Button-1>", lambda e: self.command())
            w.bind("<Enter>", self._enter)
            w.bind("<Leave>", self._leave)

    def _paint(self, bg, fg, bar):
        for w in (self, self.icon, self.label, self.bar):
            w.configure(bg=bg)
        self.bar.configure(bg=bar)
        self.icon.configure(fg=fg)
        self.label.configure(fg=fg)

    def set_active(self, on):
        self.active = on
        self._paint(CARD2 if on else SIDEBAR, TEXT if on else SUB,
                    ACCENT if on else (CARD2 if on else SIDEBAR))

    def _enter(self, _e):
        if not self.active:
            self._paint(CARD, TEXT, CARD)

    def _leave(self, _e):
        if not self.active:
            self._paint(SIDEBAR, SUB, SIDEBAR)


class App:
    def __init__(self, root):
        self.root = root
        self.bot = None
        self.bot_thread = None
        self.log_since = 0
        self.fields = {}
        self.navs = {}
        self.pages = {}
        self.current_page = None
        # 「动态奖励」手动模式的提醒窗：脚本线程只改这个标志，主线程轮询时弹/关
        self.reward_notice_wanted = False
        self._reward_popup = None

        root.title(f"A9 自动驾驶台 {VERSION_TEXT}")
        root.configure(bg=BG)
        root.geometry("%dx%d" % (px(1160), px(740)))
        root.minsize(px(960), px(620))
        try:
            root.tk.call("tk", "scaling", DPI / 72.0)
        except Exception:
            pass
        self._center()
        self._set_icon()

        self._build_sidebar()
        self._build_content()
        self.show_page("status")

        self.load_settings()
        self.root.after(400, self.poll_logs)
        self.root.after(700, self.poll_status)
        self.root.after(1000, self.poll_templates)

    def _center(self):
        self.root.update_idletasks()
        w, h = px(1160), px(740)
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        self.root.geometry("+%d+%d" % (max(0, (sw - w) // 2), max(0, (sh - h) // 3)))

    def _set_icon(self):
        """设置窗口 / 任务栏图标。

        分两步：
        1. Win32 方式：按系统当前 DPI 实际需要的尺寸（SM_CXSMICON / SM_CXICON）
           从 .ico 里加载正好那么大的图标再 WM_SETICON。
           这样 Windows 不需要缩放，图标不会发糊（Tk 只会加载一个尺寸再被缩放）。
        2. 兜底：Tk 的 iconbitmap(路径)。注意必须用位置参数，
           iconbitmap(default=...) 和 iconphoto() 实测都不会作用到已创建的窗口。
        """
        ico = os.path.join(config.BASE_DIR, "icon.ico")
        png = os.path.join(config.BASE_DIR, "icon.png")
        src = ico if os.path.exists(ico) else (png if os.path.exists(png) else None)
        if not src:
            return

        if os.name == "nt" and src.lower().endswith(".ico") and self._set_icon_win32(src):
            # Tk 之后还会陆续创建内部窗口（TtkMonitorWindow / IME 等），
            # 稍后补设几次，保证任务栏取到的也是我们的图标
            for delay in (600, 1800, 4000):
                self.root.after(delay, lambda p=src: self._set_icon_win32(p))
            return

        try:
            self.root.iconbitmap(src)
            return
        except Exception:
            pass
        # 中文路径有时 Tk 不认 → 复制到临时目录换成英文名再试
        try:
            tmp = os.path.join(os.environ.get("TEMP", "."), "a9auto_icon.ico")
            shutil.copyfile(src, tmp)
            self.root.iconbitmap(tmp)
        except Exception:
            pass

    def _set_icon_win32(self, ico_path):
        """按系统实际需要的像素尺寸设置图标（避免被 Windows 缩放而发糊）。

        关键：不能只设「主窗口」！
        Tk 还会创建 TtkMonitorWindow、Default IME、MSCTFIME UI 等窗口，
        任务栏最终取的是其中某个窗口的图标 —— 实测只设主窗口时，任务栏显示的
        仍然是 pythonw.exe 的 Python 图标。所以这里给本进程【所有】顶层窗口
        以及它们的子窗口都设一遍，任务栏才会跟着变。
        """
        try:
            u = ctypes.windll.user32
            WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
            u.LoadImageW.restype = ctypes.c_void_p
            u.LoadImageW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_uint,
                                     ctypes.c_int, ctypes.c_int, ctypes.c_uint]
            u.SendMessageW.restype = ctypes.c_void_p
            u.SendMessageW.argtypes = [ctypes.c_void_p, ctypes.c_uint,
                                       ctypes.c_void_p, ctypes.c_void_p]
            u.GetWindowThreadProcessId.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
            u.EnumWindows.argtypes = [WNDENUMPROC, ctypes.c_void_p]
            u.EnumChildWindows.argtypes = [ctypes.c_void_p, WNDENUMPROC, ctypes.c_void_p]

            IMAGE_ICON = 1
            LR_LOADFROMFILE = 0x0010
            WM_SETICON = 0x0080
            ICON_SMALL, ICON_BIG, ICON_SMALL2 = 0, 1, 2
            SM_CXICON, SM_CYICON, SM_CXSMICON, SM_CYSMICON = 11, 12, 49, 50

            self.root.update_idletasks()

            cxs, cys = u.GetSystemMetrics(SM_CXSMICON), u.GetSystemMetrics(SM_CYSMICON)
            cxb, cyb = u.GetSystemMetrics(SM_CXICON), u.GetSystemMetrics(SM_CYICON)
            small = u.LoadImageW(None, ico_path, IMAGE_ICON, cxs, cys, LR_LOADFROMFILE)
            big = u.LoadImageW(None, ico_path, IMAGE_ICON, cxb, cyb, LR_LOADFROMFILE)
            if not small and not big:
                return False

            def apply(h):
                if small:
                    u.SendMessageW(ctypes.c_void_p(h), WM_SETICON, ICON_SMALL, small)
                    u.SendMessageW(ctypes.c_void_p(h), WM_SETICON, ICON_SMALL2, small)
                if big:
                    u.SendMessageW(ctypes.c_void_p(h), WM_SETICON, ICON_BIG, big)

            pid = ctypes.windll.kernel32.GetCurrentProcessId()
            tops = []

            def on_top(h, _l):
                p = ctypes.c_ulong()
                u.GetWindowThreadProcessId(h, ctypes.byref(p))
                if p.value == pid:
                    tops.append(h)
                return True

            u.EnumWindows(WNDENUMPROC(on_top), None)

            count = 0
            for h in tops:
                apply(h)
                count += 1
                kids = []

                def on_kid(c, _l, _acc=kids):
                    _acc.append(c)
                    return True

                u.EnumChildWindows(ctypes.c_void_p(h), WNDENUMPROC(on_kid), None)
                for c in kids:
                    apply(c)
                count += len(kids)

            self._icons = (small, big)        # 句柄留引用，别被回收
            if not getattr(self, "_icon_logged", False):
                self._icon_logged = True
                log("图标已设到 %d 个窗口（小 %dx%d / 大 %dx%d）", count, cxs, cys, cxb, cyb)
            return True
        except Exception as e:
            log("设置图标失败: %s", e)
            return False

    # ================= 侧栏 =================
    def _build_sidebar(self):
        side = tk.Frame(self.root, bg=SIDEBAR, width=px(236))
        side.pack(side="left", fill="y")
        side.pack_propagate(False)

        brand = tk.Frame(side, bg=SIDEBAR)
        brand.pack(fill="x", padx=px(20), pady=(px(24), px(26)))

        logo = tk.Canvas(brand, width=px(42), height=px(42), bg=SIDEBAR,
                         highlightthickness=0, bd=0)
        logo.pack(side="left")
        round_rect(logo, 0, 0, px(42), px(42), px(11), fill=ACCENT, outline="")
        logo.create_text(px(21), px(21), text="A9", fill="#05222a", font=f_ui(13, True))

        bt = tk.Frame(brand, bg=SIDEBAR)
        bt.pack(side="left", padx=(px(12), 0))
        tk.Label(bt, text="自动驾驶台", bg=SIDEBAR, fg=TEXT, font=f_ui(13, True)).pack(anchor="w")
        tk.Label(bt, text=f"ASPHALT 9 · {VERSION_TEXT}", bg=SIDEBAR, fg=SUB,
                 font=f_mono(8)).pack(anchor="w")

        tk.Frame(side, bg=BORDER, height=1).pack(fill="x", padx=px(16))

        nav_wrap = tk.Frame(side, bg=SIDEBAR)
        nav_wrap.pack(fill="x", pady=(px(14), 0))
        for key, glyph, text in (("status", "◈", "状态总览"),
                                 ("cars", "▦", "选车管理"),
                                 ("params", "⚙", "参数设置"),
                                 ("log", "▤", "实时日志"),
                                 ("tpl", "▣", "模板状态")):
            item = NavItem(nav_wrap, glyph, text, lambda k=key: self.show_page(k))
            item.pack(fill="x", pady=px(2))
            self.navs[key] = item

        bottom = tk.Frame(side, bg=SIDEBAR)
        bottom.pack(side="bottom", fill="x", padx=px(18), pady=px(20))

        card = tk.Frame(bottom, bg=CARD, highlightbackground=BORDER, highlightthickness=1)
        card.pack(fill="x", pady=(0, px(12)))
        inner = tk.Frame(card, bg=CARD)
        inner.pack(fill="x", padx=px(14), pady=px(12))

        row = tk.Frame(inner, bg=CARD)
        row.pack(fill="x")
        self.dot = tk.Canvas(row, width=px(12), height=px(12), bg=CARD,
                             highlightthickness=0, bd=0)
        self.dot.pack(side="left")
        self.dot_id = self.dot.create_oval(1, 1, px(11), px(11), fill=SUB, outline="")
        self.lbl_state = tk.Label(row, text="待机", bg=CARD, fg=TEXT, font=f_ui(12, True))
        self.lbl_state.pack(side="left", padx=(px(8), 0))

        self.lbl_loop = tk.Label(inner, text="已完成 0 场", bg=CARD, fg=SUB, font=f_ui(9))
        self.lbl_loop.pack(anchor="w", pady=(px(6), 0))

        self.btn_start = RoundButton(bottom, "▶   启动脚本", self.on_start,
                                     px(200), px(44), ACCENT, ACCENT_H, "#05222a",
                                     f_ui(12, True), SIDEBAR)
        self.btn_start.pack()

        self.btn_stop = RoundButton(bottom, "■   停止脚本", self.on_stop,
                                    px(200), px(36), CARD2, HOVER, SUB,
                                    f_ui(10, True), SIDEBAR)
        self.btn_stop.pack(pady=(px(8), 0))
        self.btn_stop.set_enabled(False)

        # 打赏入口（点开是弹窗，不是页面）
        donate = tk.Label(bottom, text="❤ 打赏作者 ❤", bg=SIDEBAR, fg="#e08aa0",
                          font=f_ui(10, True), cursor="hand2")
        donate.pack(pady=(px(14), 0))
        donate.bind("<Button-1>", lambda e: self.open_donate())
        donate.bind("<Enter>", lambda e: donate.configure(fg="#ff9db4"))
        donate.bind("<Leave>", lambda e: donate.configure(fg="#e08aa0"))

    # ================= 打赏作者 =================
    def open_donate(self):
        """打赏弹窗：一段话 + 收款码。"""
        qr = os.path.join(config.BASE_DIR, getattr(config, "DONATE_QR", "assets/donate.png"))

        win = tk.Toplevel(self.root)
        win.title("打赏作者")
        win.configure(bg=BG)
        win.transient(self.root)
        win.resizable(False, False)

        body = tk.Frame(win, bg=BG)
        body.pack(fill="both", expand=True, padx=px(24), pady=px(20))

        tk.Label(body, text="❤", bg=BG, fg="#e05a7a", font=f_ui(24, True)).pack()
        tk.Label(body, text="如果你觉得它好用，欢迎投喂一点小鱼干喵。\n"
                            "你的每一份心意，都会变成新功能和更新的动力！",
                 bg=BG, fg=TEXT, font=f_ui(11), justify="center").pack(pady=(px(6), px(14)))

        holder = tk.Frame(body, bg=CARD, highlightbackground=BORDER, highlightthickness=1)
        holder.pack()
        pic = self._qr_image(qr, 300)
        self._donate_icon = pic            # 防止被回收
        if pic is not None:
            tk.Label(holder, image=pic, bg=CARD).pack(padx=px(14), pady=px(14))
            tk.Label(body, text="扫一扫上面的收款码", bg=BG, fg=SUB,
                     font=f_ui(9)).pack(pady=(px(8), 0))
        else:
            # 没放收款码时不显示任何"怎么放"的提示：那是作者自己的事
            tk.Label(holder, text="（收款码暂未设置）", bg=CARD, fg=SUB,
                     font=f_ui(10)).pack(padx=px(55), pady=px(60))

        btns = tk.Frame(body, bg=BG)
        btns.pack(pady=(px(16), 0))
        RoundButton(btns, "关闭", win.destroy, px(100), px(36),
                    ACCENT, ACCENT_H, "#05222a", f_ui(10, True), BG).pack()

        win.bind("<Escape>", lambda e: win.destroy())
        win.update_idletasks()
        x = self.root.winfo_rootx() + (self.root.winfo_width() - win.winfo_width()) // 2
        y = self.root.winfo_rooty() + (self.root.winfo_height() - win.winfo_height()) // 3
        win.geometry("+%d+%d" % (max(0, x), max(0, y)))
        win.focus_force()

    def _qr_image(self, path, box):
        """读收款码并缩放到 box 宽以内，返回 PhotoImage（读不到返回 None）。

        收款码是二维码，缩放用 INTER_AREA/INTER_NEAREST，别用会糊的插值。
        """
        if not os.path.exists(path):
            return None
        try:
            import cv2
            import numpy as np
            img = cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_COLOR)
            if img is None:
                return None
            h, w = img.shape[:2]
            target = px(box)
            if max(w, h) > target:
                s = target / float(max(w, h))
                img = cv2.resize(img, (max(1, int(w * s)), max(1, int(h * s))),
                                 interpolation=cv2.INTER_AREA)
            elif max(w, h) < target // 2:
                s = target / float(max(w, h))
                img = cv2.resize(img, (int(w * s), int(h * s)),
                                 interpolation=cv2.INTER_NEAREST)
            ok, buf = cv2.imencode(".png", img)
            if not ok:
                return None
            return tk.PhotoImage(data=base64.b64encode(buf.tobytes()))
        except Exception as e:
            log("收款码读取失败: %s", e)
            return None

    # 注：收款码改由使用者自己替换文件（config.DONATE_QR 指的那个），
    # 界面上不提供"选择图片"入口。

    # ================= 内容区 =================
    def _build_content(self):
        self.content = tk.Frame(self.root, bg=BG)
        self.content.pack(side="left", fill="both", expand=True)

        head = tk.Frame(self.content, bg=BG)
        head.pack(fill="x", padx=px(28), pady=(px(24), px(4)))
        self.lbl_page = tk.Label(head, text="状态总览", bg=BG, fg=TEXT, font=f_ui(17, True))
        self.lbl_page.pack(side="left")
        self.lbl_page_sub = tk.Label(head, text="", bg=BG, fg=SUB, font=f_ui(9))
        self.lbl_page_sub.pack(side="left", padx=(px(12), 0), pady=(px(6), 0))

        self.body = tk.Frame(self.content, bg=BG)
        self.body.pack(fill="both", expand=True, padx=px(28), pady=(px(10), px(20)))

        self.pages["status"] = self._page_status()
        self.pages["params"] = self._page_params()
        self.pages["log"] = self._page_log()
        self.pages["cars"] = self._page_cars()
        self.pages["tpl"] = self._page_templates()

    def _card(self, parent, title, sub=""):
        card = tk.Frame(parent, bg=CARD, highlightbackground=BORDER, highlightthickness=1)
        hd = tk.Frame(card, bg=CARD)
        hd.pack(fill="x", padx=px(18), pady=(px(15), px(10)))
        tk.Label(hd, text=title, bg=CARD, fg=TEXT, font=f_ui(11, True)).pack(side="left")
        if sub:
            tk.Label(hd, text=sub, bg=CARD, fg=SUB, font=f_ui(9)).pack(side="left", padx=(px(10), 0))
        return card

    # ---------- 状态页 ----------
    def _page_status(self):
        page = tk.Frame(self.body, bg=BG)

        hero = tk.Frame(page, bg=CARD, highlightbackground=BORDER, highlightthickness=1)
        hero.pack(fill="x")
        hl = tk.Frame(hero, bg=CARD)
        hl.pack(side="left", padx=px(24), pady=px(22))
        self.hero_state = tk.Label(hl, text="待机", bg=CARD, fg=TEXT, font=f_ui(24, True))
        self.hero_state.pack(anchor="w")
        self.hero_sub = tk.Label(hl, text="脚本未运行", bg=CARD, fg=SUB, font=f_ui(10))
        self.hero_sub.pack(anchor="w", pady=(px(6), 0))
        self.hero_btn = RoundButton(hero, "▶   启动脚本", self.on_start,
                                    px(180), px(48), ACCENT, ACCENT_H, "#05222a",
                                    f_ui(13, True), CARD)
        self.hero_btn.pack(side="right", padx=px(24), pady=px(22))

        stats = tk.Frame(page, bg=BG)
        stats.pack(fill="x", pady=(px(16), 0))
        for i in range(3):
            stats.columnconfigure(i, weight=1)

        self.stat_values = {}
        for i, (key, title) in enumerate((("loop", "当前场次"), ("nitro", "氮气坐标"), ("fg", "前台应用"))):
            c = tk.Frame(stats, bg=CARD, highlightbackground=BORDER, highlightthickness=1)
            c.grid(row=0, column=i, sticky="nsew", padx=(0 if i == 0 else px(14), 0))
            tk.Label(c, text=title, bg=CARD, fg=SUB, font=f_ui(9)).pack(anchor="w", padx=px(18), pady=(px(14), 0))
            v = tk.Label(c, text="—", bg=CARD, fg=TEXT, font=f_mono(12))
            v.pack(anchor="w", padx=px(18), pady=(px(4), px(14)))
            self.stat_values[key] = v

        info = self._card(page, "运行参数", "当前生效值")
        info.pack(fill="x", pady=(px(16), 0))
        grid = tk.Frame(info, bg=CARD)
        grid.pack(fill="x", padx=px(18), pady=(0, px(16)))
        self.info_values = {}
        pairs = [
            ("设备序列号", "DEVICE_SERIAL"), ("氮气间隔", "NITRO_INTERVAL_S"),
            ("双击间隔", "GAP_TEXT"), ("识别阈值", "MATCH_THRESHOLD"),
            ("匹配等待", "MATCHING_DELAY_S"), ("循环次数", "MAX_LOOPS"),
        ]
        for i, (label, key) in enumerate(pairs):
            cell = tk.Frame(grid, bg=CARD)
            cell.grid(row=i // 3, column=i % 3, sticky="w", padx=(0, px(36)), pady=px(4))
            tk.Label(cell, text=label, bg=CARD, fg=SUB, font=f_ui(9)).pack(anchor="w")
            v = tk.Label(cell, text="—", bg=CARD, fg=TEXT, font=f_mono(10))
            v.pack(anchor="w")
            self.info_values[key] = v
        return page

    # ---------- 可滚动区域（两个坑都在这儿处理） ----------
    def _scroll_area(self, parent, padx=0, pady=0, on_resize=None):
        """带竖向滚动的区域，返回 (canvas, inner)。

        两个坑：
        1. 内嵌窗口必须【钉住宽度】。不钉的话它按内容自然宽度显示，内容一旦比画布宽
           右边就会被裁掉 —— 而且没有横向滚动条，用户永远够不着（实测 1415 > 1276，
           右边 139px 看不见，就是这个原因）。
        2. 鼠标滚轮不能一上来就 bind_all：那样最后一个绑定的画布会抢走所有页面的滚轮。
           改成鼠标进入这块区域时才接管、离开就还回去。
        """
        wrap = tk.Frame(parent, bg=BG)
        wrap.pack(fill="both", expand=True, padx=padx, pady=pady)

        canvas = tk.Canvas(wrap, bg=BG, highlightthickness=0, bd=0)
        vsb = tk.Scrollbar(wrap, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        inner = tk.Frame(canvas, bg=BG)
        win = canvas.create_window((0, 0), window=inner, anchor="nw")

        def _on_canvas_resize(e):
            canvas.itemconfigure(win, width=e.width)      # 关键：钉住宽度
            if on_resize:
                on_resize(e.width)

        canvas.bind("<Configure>", _on_canvas_resize)
        inner.bind("<Configure>",
                   lambda e: canvas.configure(scrollregion=canvas.bbox("all")))

        def _wheel(e):
            canvas.yview_scroll(int(-e.delta / 120), "units")

        canvas.bind("<Enter>", lambda e: canvas.bind_all("<MouseWheel>", _wheel))
        canvas.bind("<Leave>", lambda e: canvas.unbind_all("<MouseWheel>"))
        return canvas, inner

    # ---------- 参数页 ----------
    def _page_params(self):
        page = tk.Frame(self.body, bg=BG)

        bar = tk.Frame(page, bg=BG)
        bar.pack(fill="x", pady=(0, px(12)))
        tk.Label(bar, text="修改后点右侧保存；运行中的脚本需停止后重新启动才生效",
                 bg=BG, fg=SUB, font=f_ui(9)).pack(side="left")
        RoundButton(bar, "保存参数", self.on_save, px(130), px(38),
                    VIOLET, "#a78bfa", "#ffffff", f_ui(11, True), BG).pack(side="right")

        self.p_canvas, self.p_inner = self._scroll_area(page, on_resize=self._fit_hint_wrap)
        return page

    # ---------- 日志页 ----------
    def _page_log(self):
        page = tk.Frame(self.body, bg=BG)

        bar = tk.Frame(page, bg=BG)
        bar.pack(fill="x", pady=(0, px(12)))
        self.var_autoscroll = tk.BooleanVar(value=True)
        tk.Checkbutton(bar, text="自动滚动到最新", variable=self.var_autoscroll,
                       bg=BG, fg=SUB, font=f_ui(9), selectcolor=CARD,
                       activebackground=BG, activeforeground=TEXT,
                       highlightthickness=0, bd=0).pack(side="left")
        RoundButton(bar, "清空", self.clear_log, px(90), px(34),
                    CARD2, HOVER, TEXT, f_ui(10), BG).pack(side="right")

        box = tk.Frame(page, bg=CARD, highlightbackground=BORDER, highlightthickness=1)
        box.pack(fill="both", expand=True)
        self.log_text = tk.Text(box, bg="#080b11", fg="#a9b6c8", font=f_mono(9),
                                relief="flat", highlightthickness=0, wrap="word",
                                insertbackground=BG, padx=px(14), pady=px(12), state="disabled")
        sb = tk.Scrollbar(box, orient="vertical", command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.log_text.pack(side="left", fill="both", expand=True)
        return page

    # ---------- 模板页 ----------
    def _page_templates(self):
        page = tk.Frame(self.body, bg=BG)
        page.columnconfigure(0, weight=1)

        c1 = self._card(page, "按钮模板", "")
        c1.grid(row=0, column=0, sticky="nsew")
        self.tpl_count = tk.Label(c1, text="0/0", bg=CARD, fg=ACCENT, font=f_mono(11, True))
        self.tpl_count.place(relx=1.0, x=-px(18), y=px(15), anchor="ne")
        self.tpl_text = tk.Text(c1, bg=CARD, fg=TEXT, font=f_mono(9), relief="flat",
                                highlightthickness=0, wrap="none", height=18,
                                insertbackground=CARD, state="disabled", padx=px(14), pady=px(14))
        self.tpl_text.pack(fill="both", expand=True)
        self.tpl_text.tag_configure("ok", foreground=OK)
        self.tpl_text.tag_configure("miss", foreground=DANGER)
        self.tpl_text.tag_configure("opt", foreground=WARN)

        return page

    # ================= 选车管理页 =================
    def _page_cars(self):
        page = tk.Frame(self.body, bg=BG)
        page.columnconfigure(0, weight=1)
        page.rowconfigure(0, weight=1)

        card = self._card(page, "车辆模板",
                          "主车在前、备用车在后；脚本按这个顺序依次尝试，没油就换下一辆")
        card.grid(row=0, column=0, sticky="nsew")

        chead = tk.Frame(card, bg=CARD)
        chead.pack(fill="x", padx=px(16), pady=(0, px(10)))
        self.car_count = tk.Label(chead, text="0 辆", bg=CARD, fg=ACCENT, font=f_mono(11, True))
        self.car_count.pack(side="left")
        RoundButton(chead, "＋ 添加车辆", self._add_car, px(120), px(34),
                    ACCENT, ACCENT_H, "#05222a", f_ui(10, True), CARD).pack(side="right")
        RoundButton(chead, "截图选车", self._capture_car_from_emu, px(110), px(34),
                    CARD2, HOVER, TEXT, f_ui(10), CARD).pack(side="right", padx=(0, px(8)))

        self.car_canvas, self.car_inner = self._scroll_area(
            card, padx=px(10), pady=(0, px(14)))

        self._car_icons = []
        self._cars_sig = None
        self._refresh_cars()      # 立即渲染，别等轮询
        return page

    # ================= 车辆管理 =================
    def _car_signature(self):
        cars = list(getattr(config, "CAR_TEMPLATES", []) or [])
        return tuple((n, os.path.exists(os.path.join(config.TEMPLATE_DIR, n + ".png")))
                     for n in cars)

    def _mini_btn(self, parent, text, cmd, danger=False):
        b = tk.Label(parent, text=text,
                     bg="#3a1a20" if danger else CARD,
                     fg=DANGER if danger else SUB,
                     font=f_ui(9), padx=px(10), pady=px(4), cursor="hand2")
        b.pack(side="left", padx=px(3))
        b.bind("<Button-1>", lambda e: cmd())
        b.bind("<Enter>", lambda e: b.configure(fg=TEXT))
        b.bind("<Leave>", lambda e: b.configure(fg=DANGER if danger else SUB))
        return b

    def _thumb(self, path, box_w=118, box_h=58):
        """把车卡图片缩成小图，列表里用作预览。"""
        if not os.path.exists(path):
            return None
        try:
            import cv2
            import numpy as np
            img = cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_COLOR)
            if img is None:
                return None
            h, w = img.shape[:2]
            s = min(px(box_w) / float(w), px(box_h) / float(h))
            nw, nh = max(1, int(w * s)), max(1, int(h * s))
            small = cv2.resize(img, (nw, nh), interpolation=cv2.INTER_AREA)
            ok, buf = cv2.imencode(".png", small)
            if not ok:
                return None
            return tk.PhotoImage(data=base64.b64encode(buf.tobytes()))
        except Exception:
            return None

    def _refresh_cars(self):
        try:
            for w in self.car_inner.winfo_children():
                w.destroy()
        except Exception:
            return
        self._car_icons = []
        cars = list(getattr(config, "CAR_TEMPLATES", []) or [])
        self._cars_sig = self._car_signature()
        self.car_count.configure(text="%d 辆" % len(cars))

        if not cars:
            tk.Label(self.car_inner, text="还没有车辆\n点右上角「＋ 添加车辆」选一张车卡图片",
                     bg=CARD, fg=SUB, font=f_ui(10), justify="center").pack(pady=px(28))
            return

        for i, name in enumerate(cars):
            path = os.path.join(config.TEMPLATE_DIR, name + ".png")
            exists = os.path.exists(path)
            row = tk.Frame(self.car_inner, bg=CARD2,
                           highlightbackground=BORDER, highlightthickness=1)
            row.pack(fill="x", pady=px(3), padx=px(4))

            pic = tk.Label(row, bg=CARD2)
            im = self._thumb(path)
            if im is not None:
                pic.configure(image=im)
                self._car_icons.append(im)
            else:
                pic.configure(text="无图", fg=DANGER, font=f_ui(9), width=8)
            pic.pack(side="left", padx=(px(10), px(10)), pady=px(7))

            info = tk.Frame(row, bg=CARD2)
            info.pack(side="left", fill="x", expand=True)
            tk.Label(info, text="%d. %s" % (i + 1, name), bg=CARD2, fg=TEXT,
                     font=f_mono(10, True)).pack(anchor="w")
            tk.Label(info, text="图片已就绪" if exists else "图片缺失",
                     bg=CARD2, fg=OK if exists else DANGER,
                     font=f_ui(8)).pack(anchor="w")

            acts = tk.Frame(row, bg=CARD2)
            acts.pack(side="right", padx=px(10))
            if i > 0:
                self._mini_btn(acts, "↑", lambda n=name: self._move_car(n, -1))
            if i < len(cars) - 1:
                self._mini_btn(acts, "↓", lambda n=name: self._move_car(n, 1))
            self._mini_btn(acts, "删除", lambda n=name: self._del_car(n), danger=True)

    def _add_car(self):
        path = filedialog.askopenfilename(
            title="选择车卡图片",
            filetypes=[("图片", "*.png *.jpg *.jpeg *.bmp *.webp"), ("所有文件", "*.*")])
        if not path:
            return
        try:
            import cv2
            import numpy as np
            img = cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_COLOR)
        except Exception as e:
            messagebox.showerror("添加失败", "读图出错：%s" % e)
            return
        if img is None:
            messagebox.showerror("添加失败", "这张图片读不出来，换一张试试。")
            return

        self._save_new_car(img)

    def _next_car_name(self):
        cars = list(getattr(config, "CAR_TEMPLATES", []) or [])
        n = 1
        while ("car_%d" % n) in cars:
            n += 1
        return "car_%d" % n

    def _save_new_car(self, crop, verify=True):
        """把框好的车卡存成新模板。

        verify=True 时会拿一张新截图验一下匹配度（选文件那条路用）；
        从「截图选车」来的图本身就是当前画面裁的，再验就是白验，所以传 False。
        """
        import cv2
        name = self._next_car_name()
        try:
            cv2.imwrite(os.path.join(config.TEMPLATE_DIR, name + ".png"), crop)
        except Exception as e:
            messagebox.showerror("添加失败", "保存图片出错：%s" % e)
            return None
        cars = list(getattr(config, "CAR_TEMPLATES", []) or [])
        cars.append(name)
        config.CAR_TEMPLATES = cars
        save_settings({"CAR_TEMPLATES": cars})
        log("已添加车辆 %s（%dx%d 像素）", name, crop.shape[1], crop.shape[0])
        self._refresh_cars()
        if verify:
            self._verify_car(name, crop)
        return name

    def _crop_quality(self, crop, screen):
        """给刚框的图做个快速体检（逻辑在 vision.crop_quality，那边有测试）。"""
        from vision import crop_quality
        return crop_quality(crop, screen)

    # ---------- 从模拟器截图、当场框选 ----------
    def _capture_car_from_emu(self):
        """抓一张模拟器当前画面，在界面里直接框选车卡。

        比「先在外面截图、再回来选文件」省事：不用离开这个界面。
        """
        if getattr(self, "_cap_running", False):
            return
        self._cap_running = True
        self._cap_result = None
        log("正在从模拟器截图 ...")
        threading.Thread(target=self._cap_worker, daemon=True).start()
        self.root.after(150, self._poll_capture)

    def _cap_worker(self):
        try:
            import cv2
            import numpy as np
            from adb_helper import ADB
            data = ADB().screencap_bytes()
            img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
            self._cap_result = ("ok", img) if img is not None else ("err", "截图解析失败")
        except Exception as e:
            self._cap_result = ("err", str(e))

    def _poll_capture(self):
        """在主线程里取后台截图结果（不跨线程操作 Tk）。"""
        r = getattr(self, "_cap_result", None)
        if r is None:
            self.root.after(150, self._poll_capture)
            return
        self._cap_result = None
        self._cap_running = False
        kind, payload = r
        if kind == "err":
            messagebox.showerror("截图失败",
                                 "拿不到模拟器画面：\n%s\n\n先确认雷电模拟器已启动、adb 能连上。"
                                 % payload)
            return
        self._open_crop_window(payload)

    def _open_crop_window(self, screen):
        """把截图显示出来，让用户拖框选车卡。"""
        import cv2
        import numpy as np

        sh, sw = screen.shape[:2]
        scale = min(px(760) / float(sw), px(520) / float(sh), 1.0)
        dw, dh = max(1, int(sw * scale)), max(1, int(sh * scale))

        win = tk.Toplevel(self.root)
        win.title("截图选车 — 拖动鼠标框住整张车卡")
        win.configure(bg=BG)
        win.transient(self.root)
        win.resizable(False, False)
        win.grab_set()

        tk.Label(win,
                 text="按住鼠标左键拖动，把【一张完整车卡】框起来\n"
                      "（车 + 右边的图纸海报一起框；每辆车框得一样大最稳）\n"
                      "现在是 %d×%d，框多大都是按原始像素存的，不用管缩放" % (sw, sh),
                 bg=BG, fg=SUB, font=f_ui(9), justify="left").pack(
            anchor="w", padx=px(16), pady=(px(14), px(8)))

        small = cv2.resize(screen, (dw, dh), interpolation=cv2.INTER_AREA)
        ok, buf = cv2.imencode(".png", small)
        if not ok:
            win.destroy()
            messagebox.showerror("截图失败", "画面编码失败，重试一次。")
            return
        photo = tk.PhotoImage(data=base64.b64encode(buf.tobytes()))

        canvas = tk.Canvas(win, width=dw, height=dh, bg="#05070b",
                           highlightthickness=1, highlightbackground=BORDER,
                           cursor="crosshair")
        canvas.pack(padx=px(16))
        canvas.create_image(0, 0, anchor="nw", image=photo)
        canvas.image = photo                      # 防止被回收

        info = tk.Label(win, text="还没框选", bg=BG, fg=ACCENT, font=f_mono(9))
        info.pack(anchor="w", padx=px(16), pady=(px(8), 0))

        state = {"start": None, "rect": None, "id": None}

        def on_press(e):
            state["start"] = (e.x, e.y)
            if state["id"] is not None:
                canvas.delete(state["id"])
            state["id"] = canvas.create_rectangle(e.x, e.y, e.x, e.y,
                                                  outline=ACCENT, width=px(2))
            state["rect"] = None

        def on_drag(e):
            if state["start"] is None:
                return
            x0, y0 = state["start"]
            canvas.coords(state["id"], x0, y0, e.x, e.y)
            # 换算回原始分辨率显示尺寸
            w = abs(e.x - x0) / scale
            h = abs(e.y - y0) / scale
            info.configure(text="当前框选：%d × %d 像素（左上角 %d, %d）"
                                % (w, h, min(x0, e.x) / scale, min(y0, e.y) / scale))

        def on_release(e):
            if state["start"] is None:
                return
            x0, y0 = state["start"]
            if abs(e.x - x0) < 5 or abs(e.y - y0) < 5:
                state["rect"] = None
                info.configure(text="框太小了，重新拖一个")
                return
            state["rect"] = (min(x0, e.x), min(y0, e.y), max(x0, e.x), max(y0, e.y))

        canvas.bind("<Button-1>", on_press)
        canvas.bind("<B1-Motion>", on_drag)
        canvas.bind("<ButtonRelease-1>", on_release)
        canvas.bind("<Button-3>", lambda e: (canvas.delete("all"),
                                             canvas.create_image(0, 0, anchor="nw",
                                                                 image=photo),
                                             state.update({"rect": None}),
                                             info.configure(text="已清空，重新拖一个")))

        btns = tk.Frame(win, bg=BG)
        btns.pack(fill="x", padx=px(16), pady=(px(10), px(14)))

        def do_save(_e=None):
            r = state["rect"]
            if not r:
                messagebox.showinfo("还没框选", "先用鼠标拖一个框，把车卡框起来。", parent=win)
                return
            x0 = int(r[0] / scale)
            y0 = int(r[1] / scale)
            x1 = int(r[2] / scale)
            y1 = int(r[3] / scale)
            x0, x1 = max(0, min(x0, x1)), min(sw, max(x0, x1))
            y0, y1 = max(0, min(y0, y1)), min(sh, max(y0, y1))
            if x1 - x0 < 40 or y1 - y0 < 40:
                messagebox.showinfo("框太小", "框大一点，把整张车卡包进去。", parent=win)
                return
            crop = screen[y0:y1, x0:x1].copy()
            level, tip = self._crop_quality(crop, screen)
            win.destroy()
            name = self._save_new_car(crop, verify=False)
            if name is None:
                return
            extra = ("\n\n提示：" + tip) if level == "warn" else ""
            messagebox.showinfo(
                "已添加",
                "已添加 %s（%d × %d 像素）。%s\n\n"
                "下次脚本选车时，日志里会打印它的匹配置信度，正常应该在 0.95 以上。"
                % (name, crop.shape[1], crop.shape[0], extra))

        def do_reshot(_e=None):
            win.destroy()
            self.root.after(100, self._capture_car_from_emu)

        RoundButton(btns, "保存这张", do_save, px(120), px(36),
                    ACCENT, ACCENT_H, "#05222a", f_ui(10, True), BG).pack(side="right")
        RoundButton(btns, "重新截图", do_reshot, px(110), px(36),
                    CARD2, HOVER, TEXT, f_ui(10), BG).pack(side="right", padx=(0, px(8)))
        RoundButton(btns, "取消", win.destroy, px(90), px(36),
                    CARD2, HOVER, TEXT, f_ui(10), BG).pack(side="right", padx=(0, px(8)))
        tk.Label(btns, text="回车=保存    Esc=取消    右键=清空重框",
                 bg=BG, fg="#5c6779", font=f_ui(8)).pack(side="left")

        win.bind("<Return>", do_save)
        win.bind("<Escape>", lambda e: win.destroy())
        win.focus_force()
        canvas.focus_set()

    def _verify_car(self, name, img):
        """刚添加完（从文件添加那条路），顺手在当前画面上测一下匹配度。

        如果现在正好停在选车界面，这条信息很有用：能确认你选的图
        确实对应画面上的某辆车。
        """
        try:
            import cv2
            import numpy as np
            from adb_helper import ADB
            screen_bgr = cv2.imdecode(np.frombuffer(ADB().screencap_bytes(), np.uint8),
                                      cv2.IMREAD_COLOR)
            gray = cv2.cvtColor(screen_bgr, cv2.COLOR_BGR2GRAY)
            tpl = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            if gray.shape[0] < tpl.shape[0] or gray.shape[1] < tpl.shape[1]:
                messagebox.showinfo("已添加", "已添加 %s。" % name)
                return
            mv = float(cv2.minMaxLoc(cv2.matchTemplate(gray, tpl, cv2.TM_CCOEFF_NORMED))[1])
            log("车辆 %s 当前画面匹配度 %.3f", name, mv)
            if mv >= 0.85:
                messagebox.showinfo("添加成功",
                                    "已添加 %s\n当前画面匹配度 %.3f ✓ 这张图可用" % (name, mv))
            else:
                messagebox.showwarning(
                    "已添加，请确认图片",
                    "已添加 %s\n\n但当前画面匹配度只有 %.3f。\n\n"
                    "· 如果现在就停在「选车界面」且能看到这辆车 → 这张图可能不对，"
                    "建议改用「采集车辆.exe」直接框选。\n"
                    "· 如果现在不在选车界面 → 忽略这个提示即可。" % (name, mv))
        except Exception as e:
            log("匹配度检测失败: %s", e)

    def _del_car(self, name):
        if not messagebox.askyesno("删除车辆",
                                   "确定删除 %s 吗？\n它的图片文件也会一起删掉。" % name):
            return
        cars = [c for c in (getattr(config, "CAR_TEMPLATES", []) or []) if c != name]
        config.CAR_TEMPLATES = cars
        p = os.path.join(config.TEMPLATE_DIR, name + ".png")
        try:
            if os.path.exists(p):
                os.remove(p)
        except Exception as e:
            log("删除图片失败: %s", e)
        save_settings({"CAR_TEMPLATES": cars})
        log("已删除车辆 %s", name)
        self._refresh_cars()

    def _move_car(self, name, delta):
        cars = list(getattr(config, "CAR_TEMPLATES", []) or [])
        if name not in cars:
            return
        i = cars.index(name)
        j = i + delta
        if j < 0 or j >= len(cars):
            return
        cars[i], cars[j] = cars[j], cars[i]
        config.CAR_TEMPLATES = cars
        save_settings({"CAR_TEMPLATES": cars})
        log("已调整车辆顺序：%s", " → ".join(cars))
        self._refresh_cars()

    # ================= 动态奖励提醒窗 =================
    def set_reward_notice(self, show):
        """脚本线程调用（只改标志，不碰 Tk 控件）。"""
        self.reward_notice_wanted = bool(show)

    def _sync_reward_popup(self):
        """在主线程里根据标志弹/关提醒窗。"""
        want = bool(getattr(self, "reward_notice_wanted", False))
        popup = getattr(self, "_reward_popup", None)
        if want and popup is None:
            self._open_reward_popup()
        elif not want and popup is not None:
            try:
                popup.destroy()
            except Exception:
                pass
            self._reward_popup = None

    def _open_reward_popup(self):
        """弹到最前面的提醒窗：游戏里出「动态奖励」了，请你手动选一个。"""
        win = tk.Toplevel(self.root)
        win.title("该选动态奖励了")
        win.configure(bg=BG)
        win.attributes("-topmost", True)
        win.resizable(False, False)
        self._reward_popup = win

        body = tk.Frame(win, bg=BG)
        body.pack(fill="both", expand=True, padx=px(26), pady=px(22))
        tk.Label(body, text="⚠", bg=BG, fg=WARN, font=f_ui(26, True)).pack()
        tk.Label(body, text="游戏里出现「动态奖励」了",
                 bg=BG, fg=TEXT, font=f_ui(13, True)).pack(pady=(px(6), px(6)))
        tk.Label(body, text="请切到模拟器，挑一张奖励卡片（有的界面还要点一下『确认』）。\n"
                            "选完这个窗口会自己关掉，脚本会继续跑。",
                 bg=BG, fg=SUB, font=f_ui(10), justify="center").pack()
        RoundButton(body, "知道了", win.destroy, px(110), px(38),
                    ACCENT, ACCENT_H, "#05222a", f_ui(10, True), BG).pack(pady=(px(16), 0))

        win.update_idletasks()
        sw = win.winfo_screenwidth()
        x = (sw - win.winfo_width()) // 2
        win.geometry("+%d+%d" % (max(0, x), px(90)))
        win.lift()
        win.focus_force()
        for delay in (200, 800, 2000):        # 有些系统会抢焦点，多抬几次
            win.after(delay, lambda: (win.lift(), win.attributes("-topmost", True)))
        try:
            import winsound
            winsound.MessageBeep(winsound.MB_ICONASTERISK)
        except Exception:
            pass
        log("已弹出「动态奖励」提醒窗，等你手动选")

    # ================= 页面切换 =================
    TITLES = {
        "status": ("状态总览", "脚本运行情况一览"),
        "params": ("参数设置", "氮气 / 识别 / 超时 / 匹配 / 截图频率 / 闪退恢复 / 选车 / 动态奖励 / 循环 / 设备"),
        "log": ("实时日志", "脚本输出实时滚动"),
        "cars": ("选车管理", "添加 / 删除车辆图片，调整尝试顺序（主车在前）"),
        "tpl": ("模板状态", "图像识别所需的模板采集情况"),
    }

    def show_page(self, key):
        if self.current_page == key:
            return
        for k, p in self.pages.items():
            if k == key:
                p.pack(fill="both", expand=True)
            else:
                p.pack_forget()
        for k, n in self.navs.items():
            n.set_active(k == key)
        title, sub = self.TITLES[key]
        self.lbl_page.configure(text=title)
        self.lbl_page_sub.configure(text=sub)
        self.current_page = key

    # ================= 参数 =================
    def _fit_hint_wrap(self, canvas_width):
        """按画布宽度调整提示文字的换行宽度。

        参数页是 3 列的，窗口拉窄时如果提示文字还坚持原来那么宽，
        整个网格会被撑得比画布宽 —— 右边又会看不到。
        """
        labels = getattr(self, "_hint_labels", None)
        if not labels:
            return
        wrap = max(px(110), (canvas_width - px(80)) // 3 - px(16))
        for lb in labels:
            try:
                if abs(int(lb.cget("wraplength")) - wrap) > 2:
                    lb.configure(wraplength=wrap)
            except Exception:
                pass

    def load_settings(self):
        for w in self.p_inner.winfo_children():
            w.destroy()
        self.fields = {}
        self._hint_labels = []

        values = current_settings()
        # 带 hidden 标记的字段不在参数页显示（例如车辆列表，已挪到「选车管理」页）
        visible = [i for i in SETTINGS_SCHEMA if not i.get("hidden")]
        groups = []
        for item in visible:
            if item["group"] not in groups:
                groups.append(item["group"])

        for g in groups:
            items = [i for i in visible if i["group"] == g]
            card = self._card(self.p_inner, g, "")
            card.pack(fill="x", pady=(0, px(12)))
            grid = tk.Frame(card, bg=CARD)
            grid.pack(fill="x", padx=px(18), pady=(0, px(16)))
            for c in range(3):
                grid.columnconfigure(c, weight=1)

            row = col = 0
            for item in items:
                cell = tk.Frame(grid, bg=CARD)
                cell.grid(row=row, column=col, sticky="ew", padx=(0, px(18)), pady=(0, px(10)))
                tk.Label(cell, text=item["label"], bg=CARD, fg=SUB, font=f_ui(9)).pack(anchor="w")
                val = values.get(item["key"], "")

                if item["type"] == "list":
                    w = tk.Text(cell, bg=CARD2, fg=TEXT, font=f_mono(9), height=4,
                                relief="flat", highlightthickness=1, highlightbackground=BORDER,
                                highlightcolor=ACCENT, insertbackground=TEXT, padx=px(8), pady=px(6))
                    w.insert("1.0", "\n".join(val if isinstance(val, list) else []))
                    w.pack(fill="x", pady=(px(5), 0))
                elif item["type"] == "choice":
                    opts = item.get("options", [])
                    labels = [lab for _, lab in opts]
                    cur = dict((v, lab) for v, lab in opts).get(val, labels[0] if labels else "")
                    var = tk.StringVar(value=cur)
                    om = tk.OptionMenu(cell, var, *(labels or [""]))
                    om.configure(bg=CARD2, fg=TEXT, activebackground=HOVER, activeforeground=TEXT,
                                 font=f_mono(10), relief="flat", highlightthickness=1,
                                 highlightbackground=BORDER, anchor="w", padx=px(8), bd=0)
                    om["menu"].configure(bg=CARD2, fg=TEXT, font=f_mono(10),
                                         activebackground=ACCENT, activeforeground="#05222a", bd=0)
                    om.pack(fill="x", ipady=px(3), pady=(px(5), 0))
                    w = var                    # 存 StringVar，collect 时再映射回值
                else:
                    w = tk.Entry(cell, bg=CARD2, fg=TEXT, font=f_mono(10),
                                 relief="flat", highlightthickness=1, highlightbackground=BORDER,
                                 highlightcolor=ACCENT, insertbackground=TEXT)
                    w.insert(0, "" if val is None else str(val))
                    w.pack(fill="x", ipady=px(6), pady=(px(5), 0))

                if item.get("hint"):
                    hl = tk.Label(cell, text=item["hint"], bg=CARD, fg="#5c6779",
                                  font=f_ui(8), justify="left", anchor="w",
                                  wraplength=px(200))
                    hl.pack(anchor="w", pady=(px(3), 0))
                    if not hasattr(self, "_hint_labels"):
                        self._hint_labels = []
                    self._hint_labels.append(hl)

                self.fields[item["key"]] = (item, w)
                col += 1
                if col >= 3:
                    col = 0
                    row += 1

    def collect_settings(self):
        data = {}
        for key, (item, w) in self.fields.items():
            if item["type"] == "list":
                data[key] = w.get("1.0", "end").splitlines()
            elif item["type"] == "choice":
                # 界面上显示的是中文标签，存回去要是 auto/manual 这种值
                label = w.get()
                data[key] = dict((lab, val) for val, lab in item.get("options", [])).get(label, label)
            else:
                data[key] = w.get()
        return data

    # ================= 操作 =================
    def on_save(self):
        try:
            save_settings(self.collect_settings())
        except Exception as e:
            messagebox.showerror("保存失败", str(e))
            return
        self._refresh_static()
        messagebox.showinfo("已保存", "参数已保存，重启脚本后生效。")

    def on_start(self):
        if self.bot_thread and self.bot_thread.is_alive():
            return
        try:
            from bot import GameBot
            self.bot = GameBot()
        except Exception as e:
            messagebox.showerror("启动失败", "无法初始化脚本：\n%s" % e)
            return
        self.bot.stop = False
        # 让「动态奖励」手动模式能弹提醒窗
        self.bot.reward_notify = self.set_reward_notice
        self.bot_thread = threading.Thread(target=self._run_bot, daemon=True)
        self.bot_thread.start()

    def _run_bot(self):
        try:
            self.bot.run()
        except Exception as e:
            log("脚本异常退出: %s", e)

    def on_stop(self):
        if self.bot:
            self.bot.stop = True
            log("已发送停止指令（本场结束后停止）")

    def clear_log(self):
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")

    # ================= 刷新 =================
    def _refresh_static(self):
        self.info_values["DEVICE_SERIAL"].configure(text=str(config.DEVICE_SERIAL))
        self.info_values["NITRO_INTERVAL_S"].configure(text="%ds" % config.NITRO_INTERVAL_S)
        self.info_values["GAP_TEXT"].configure(
            text="%d~%dms" % (config.NITRO_GAP_MIN_MS, config.NITRO_GAP_MAX_MS))
        self.info_values["MATCH_THRESHOLD"].configure(text=str(config.MATCH_THRESHOLD))
        self.info_values["MATCHING_DELAY_S"].configure(text="%ds" % config.MATCHING_DELAY_S)
        self.info_values["MAX_LOOPS"].configure(
            text="无限" if config.MAX_LOOPS == 0 else str(config.MAX_LOOPS))

    def poll_logs(self):
        try:
            logs, latest = get_logs_since(self.log_since)
            if logs:
                self.log_text.configure(state="normal")
                self.log_text.insert("end", "\n".join(logs) + "\n")
                if self.var_autoscroll.get():
                    self.log_text.see("end")
                self.log_text.configure(state="disabled")
                self.log_since = latest
        except Exception:
            pass
        self.root.after(500, self.poll_logs)

    def poll_status(self):
        running = bool(self.bot_thread and self.bot_thread.is_alive())
        stopping = running and bool(self.bot and self.bot.stop)

        if stopping:
            color, word, hero = WARN, "停止中", "正在停止"
        elif running:
            color, word, hero = ACCENT, "运行中", "正在挂机"
        else:
            color, word, hero = SUB, "待机", "待机"

        self.dot.itemconfigure(self.dot_id, fill=color)
        self.lbl_state.configure(text=word, fg=TEXT if not running else color)
        self.hero_state.configure(text=hero, fg=TEXT if not running else color)
        self.hero_sub.configure(text="脚本运行中，本场结束后才会停止" if stopping else
                                     ("自动刷段位进行中" if running else "脚本未运行"))

        loop_n = self.bot.loop_count if self.bot else 0
        self.lbl_loop.configure(text="已完成 %d 场" % loop_n)
        self.stat_values["loop"].configure(text=str(loop_n))
        self.stat_values["nitro"].configure(text="%d , %d" % (config.NITRO_X, config.NITRO_Y))

        try:
            from adb_helper import ADB
            fg = ADB().foreground_package() or "—"
        except Exception:
            fg = "—"
        self.stat_values["fg"].configure(text=fg)

        self.btn_start.set_enabled(not running)
        self.hero_btn.set_enabled(not running)
        self.btn_stop.set_enabled(running)
        self._sync_reward_popup()
        self.root.after(1000, self.poll_status)

    def poll_templates(self):
        try:
            from vision import Vision
            vis = Vision()

            self.tpl_text.configure(state="normal")
            self.tpl_text.delete("1.0", "end")
            have = total = 0
            for key, (fname, desc) in config.TEMPLATES.items():
                total += 1
                if vis.template_exists(key):
                    have += 1
                    self.tpl_text.insert("end", " ●  %-20s  已采集\n" % key, "ok")
                else:
                    req = key in config.REQUIRED_TEMPLATES
                    self.tpl_text.insert("end", " %s  %-20s  %s\n" %
                                         ("●" if req else "○", key, "缺失" if req else "可选"), 
                                         "miss" if req else "opt")
            self.tpl_text.configure(state="disabled")
            self.tpl_count.configure(text="%d/%d" % (have, total))

            # 车辆列表有变化才重建（避免每 4 秒重画一次造成闪烁）
            if self._car_signature() != self._cars_sig:
                self._refresh_cars()

            self._refresh_static()
        except Exception:
            pass
        self.root.after(4000, self.poll_templates)


def _set_app_id():
    """让 Windows 把本进程当成一个独立应用。
    不做这一步，任务栏会用 pythonw.exe 的图标（默认 Python 图标）。"""
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("A9.AutoDrive.Console")
    except Exception:
        pass


def main():
    try:
        _set_app_id()
        ensure_dirs()
        root = tk.Tk()
        App(root)
        root.mainloop()
    except Exception:
        import traceback
        tb = traceback.format_exc()
        try:
            with open(os.path.join(config.BASE_DIR, "gui_error.log"), "w", encoding="utf-8") as f:
                f.write(tb)
        except Exception:
            pass
        try:
            messagebox.showerror("A9 自动驾驶台 - 启动失败", tb)
        except Exception:
            pass
        raise


if __name__ == "__main__":
    main()
