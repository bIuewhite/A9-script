# -*- coding: utf-8 -*-
"""
vision.py —— 模板匹配识别
"""
import os
import cv2

import config
from util import log


class Vision:
    def __init__(self):
        self._cache = {}

    # ---------------- 模板文件 ----------------
    def template_file(self, key):
        if key not in config.TEMPLATES:
            return None
        return os.path.join(config.TEMPLATE_DIR, config.TEMPLATES[key][0])

    def template_exists(self, key):
        f = self.template_file(key)
        return bool(f and os.path.exists(f))

    def load_template(self, key):
        """加载模板为灰度图；文件缺失/读取失败返回 None。"""
        f = self.template_file(key)
        if not f or not os.path.exists(f):
            return None
        if key not in self._cache:
            img = cv2.imread(f, cv2.IMREAD_GRAYSCALE)
            if img is None:
                log("警告：模板读取失败 %s", f)
                return None
            self._cache[key] = img
        return self._cache[key]

    # ---------------- 匹配 ----------------
    def find(self, key, screen_gray, threshold=None):
        """在灰度截图中查找模板，返回 (x, y, confidence) 或 None。"""
        tpl = self.load_template(key)
        if tpl is None:
            return None
        if (screen_gray is None
                or screen_gray.shape[0] < tpl.shape[0]
                or screen_gray.shape[1] < tpl.shape[1]):
            return None
        th = threshold if threshold is not None else config.TEMPLATE_THRESHOLDS.get(key, config.MATCH_THRESHOLD)
        res = cv2.matchTemplate(screen_gray, tpl, cv2.TM_CCOEFF_NORMED)
        _, maxv, _, maxloc = cv2.minMaxLoc(res)
        if maxv < th:
            return None
        h, w = tpl.shape
        return (int(maxloc[0] + w / 2), int(maxloc[1] + h / 2), float(maxv))

    def has(self, key, screen_gray, threshold=None):
        return self.find(key, screen_gray, threshold) is not None

    def find_file(self, filename, screen_gray, threshold=None, min_margin=0.0):
        """按文件名（templates 目录下）匹配任意图片，返回 (x, y, conf) 或 None。

        min_margin > 0 时做「歧义保护」：最佳位置还必须比第二好的（互不重叠的）
        位置高出 min_margin 才算数。车辆卡片就是靠这个避免把别的车当目标车。
        """
        path = os.path.join(config.TEMPLATE_DIR, filename)
        if not os.path.exists(path):
            return None
        img = self._cache.get(filename)
        if img is None:
            img = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
            if img is None:
                return None
            self._cache[filename] = img
        if (screen_gray is None
                or screen_gray.shape[0] < img.shape[0]
                or screen_gray.shape[1] < img.shape[1]):
            return None
        th = threshold if threshold is not None else config.MATCH_THRESHOLD
        res = cv2.matchTemplate(screen_gray, img, cv2.TM_CCOEFF_NORMED)
        _, maxv, _, maxloc = cv2.minMaxLoc(res)
        if maxv < th:
            return None
        h, w = img.shape
        if min_margin > 0:
            # 把最佳位置挖掉，再看剩下的最高分，判断是不是「独一份」
            r = res.copy()
            y0 = max(0, maxloc[1] - h // 2)
            y1 = min(r.shape[0], maxloc[1] + h // 2)
            x0 = max(0, maxloc[0] - w // 2)
            x1 = min(r.shape[1], maxloc[0] + w // 2)
            r[y0:y1, x0:x1] = -1.0
            second = float(cv2.minMaxLoc(r)[1])
            if maxv - second < min_margin:
                log("  [%s] 匹配有歧义：最佳 %.3f / 次佳 %.3f（只差 %.3f），当作没找到",
                    filename, maxv, second, maxv - second)
                return None
        return (int(maxloc[0] + w / 2), int(maxloc[1] + h / 2), float(maxv))


# ==================== 车卡裁剪质量检查 ====================
def crop_quality(crop, screen, min_w=300, min_h=180, blur_std=12.0, dup=0.90):
    """给用户刚框出来的车卡做个快速体检，返回 (等级, 提示语)。

    等级是 "ok" 或 "warn"。主要防三种低级错误：
      · 框得太小 —— 车卡一般是 600×350 上下，太小说明没框全
      · 框到了空白/纯色背景 —— 这种图没有识别价值
      · 框到了到处都是的通用界面元素 —— 在画面上还能匹到别处

    crop 是框出来的图，screen 是它来自的整张截图（可以不传）。
    """
    if crop is None or getattr(crop, "size", 0) == 0:
        return "warn", "框选区域是空的"
    h, w = crop.shape[:2]
    if w < min_w or h < min_h:
        return "warn", f"框得偏小（{w}×{h}，车卡一般 600×350 上下），建议重新框一次"

    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY) if crop.ndim == 3 else crop
    if float(gray.std()) < blur_std:
        return "warn", "这块区域几乎没有内容（可能是空白背景），确认框对了吗？"

    if screen is None:
        return "ok", ""
    sgray = cv2.cvtColor(screen, cv2.COLOR_BGR2GRAY) if screen.ndim == 3 else screen
    if sgray.shape[0] < h or sgray.shape[1] < w:
        return "ok", ""
    try:
        res = cv2.matchTemplate(sgray, gray, cv2.TM_CCOEFF_NORMED)
        _, _, _, bestloc = cv2.minMaxLoc(res)
        # 把最佳位置挖掉，看还有没有别处也很像（只框到通用 UI 元素就会这样）
        r = res.copy()
        y0 = max(0, bestloc[1] - h // 2)
        x0 = max(0, bestloc[0] - w // 2)
        r[y0:bestloc[1] + h // 2, x0:bestloc[0] + w // 2] = -1.0
        second = float(cv2.minMaxLoc(r)[1])
    except cv2.error:
        return "ok", ""
    if second > dup:
        return "warn", (f"这张图在画面上还能匹到别处（相似度 {second:.2f}），"
                        f"可能框到了通用的界面元素，建议只框车卡本身")
    return "ok", ""
