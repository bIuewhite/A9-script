# -*- coding: utf-8 -*-
"""模板匹配逻辑的离线测试（不需要模拟器、不需要游戏）。

这些测试用随机噪声图合成「屏幕」和「模板」，专门盯住几个踩过坑的行为：
  · 目标在画面上 → 返回的位置必须是模板中心（点击靠它对）
  · 目标不在画面上 → 必须返回 None，不能瞎给一个位置
  · 画面里有两处长得一样 → 有歧义时必须返回 None（防误判保护）
  · 目标被画面边缘裁掉 → 匹配不到（所以脚本要翻页找车）
"""
import os
import unittest

import cv2
import numpy as np

import config
from vision import Vision, crop_quality
from tests import cleanup, ensure_tmp_root, unique_name


def noise(h, w, seed):
    """造一张随机噪声灰度图，用来当「屏幕」。"""
    rng = np.random.default_rng(seed)
    return rng.integers(0, 256, (h, w), dtype=np.uint8)


class VisionTestCase(unittest.TestCase):
    def setUp(self):
        # 把模板目录指到临时目录，避免动到仓库里真正的模板
        self._old_dir = config.TEMPLATE_DIR
        config.TEMPLATE_DIR = ensure_tmp_root()
        self.vis = Vision()
        self._made = []

    def tearDown(self):
        config.TEMPLATE_DIR = self._old_dir
        for p in self._made:
            try:
                os.remove(p)
            except OSError:
                pass
        cleanup()

    def write_tpl(self, img, tag="tpl.png"):
        """把模板写成文件，返回文件名（find_file 要的就是文件名）。"""
        name = unique_name(tag)
        path = os.path.join(config.TEMPLATE_DIR, name)
        self.assertTrue(cv2.imwrite(path, img), f"写模板失败: {path}")
        self._made.append(path)
        return name

    # ---------------------------------------------------------------
    def test_找到目标时返回模板中心(self):
        screen = noise(320, 480, 1)
        # 模板放在 (x=150, y=100)，尺寸 200x100
        name = self.write_tpl(screen[100:200, 150:350])

        pos = self.vis.find_file(name, screen, threshold=0.9)

        self.assertIsNotNone(pos, "完全一样的图必须能匹到")
        x, y, conf = pos
        self.assertEqual((x, y), (250, 150), "返回的应该是模板中心，不是左上角")
        self.assertGreater(conf, 0.99)

    def test_目标不在画面上时必须返回None(self):
        screen = noise(320, 480, 2)
        name = self.write_tpl(noise(100, 200, 3))   # 来自另一张图的「模板」

        self.assertIsNone(self.vis.find_file(name, screen, threshold=0.92),
                          "匹不到就必须返回 None —— 否则脚本会照着假坐标乱点")

    def test_画面里有两处一样时判为歧义(self):
        screen = noise(320, 960, 4)
        patch = noise(100, 200, 5)
        screen[80:180, 40:240] = patch       # 第一处
        screen[80:180, 560:760] = patch      # 第二处（离得够远，互不重叠）
        name = self.write_tpl(patch)

        # 不做歧义保护 → 会给出一个位置
        loose = self.vis.find_file(name, screen, threshold=0.9, min_margin=0.0)
        self.assertIsNotNone(loose)

        # 做歧义保护 → 两处分数一样高，判为歧义，返回 None
        strict = self.vis.find_file(name, screen, threshold=0.9, min_margin=0.05)
        self.assertIsNone(strict, "有两处长得一样时应当放弃，而不是赌一个")

    def test_目标被画面边缘裁掉时匹配不到(self):
        screen = noise(320, 480, 6)
        patch = noise(100, 200, 7)                 # 200 宽
        screen[100:200, 430:480] = patch[:, :50]   # 只露出左 50 像素
        name = self.write_tpl(patch)

        self.assertIsNone(self.vis.find_file(name, screen, threshold=0.92),
                          "模板比可见区域大时匹不到，所以需要翻页找车")

    def test_画面比模板小时返回None(self):
        small = noise(50, 60, 8)
        name = self.write_tpl(noise(200, 300, 9))
        self.assertIsNone(self.vis.find_file(name, small, threshold=0.5))

    def test_模板文件不存在时返回None(self):
        screen = noise(320, 480, 10)
        self.assertIsNone(self.vis.find_file("没有这个文件.png", screen))

    def test_阈值高于实际相似度时拒绝_低于时命中(self):
        screen = noise(320, 480, 11)
        # 给原图叠一层噪声，让它变成「有点像但不一样」
        #
        # 注意：不能靠「整块像素 +12」来制造差异 ——
        # TM_CCOEFF_NORMED 会先减掉均值，整块加常数完全不影响相似度（实测仍是 0.9998）。
        rng = np.random.default_rng(12)
        patch = screen[100:200, 150:350].astype(np.int16)
        patch = np.clip(patch + rng.integers(-80, 81, patch.shape), 0, 255).astype(np.uint8)
        name = self.write_tpl(patch)

        pos = self.vis.find_file(name, screen, threshold=0.0)
        self.assertIsNotNone(pos)
        conf = pos[2]
        self.assertTrue(0.3 < conf < 0.99,
                        f"这张图应该只是「有点像」（实际 {conf:.3f}），否则这个测试没意义")

        self.assertIsNotNone(self.vis.find_file(name, screen, threshold=conf - 0.02),
                             "阈值低于实际相似度时应当命中")
        self.assertIsNone(self.vis.find_file(name, screen, threshold=conf + 0.02),
                          "阈值高于实际相似度时应当拒绝")


class CropQualityTest(unittest.TestCase):
    """「截图选车」框完之后的质量体检（gui.py 里点保存时调用的就是它）。"""

    def test_框得太小会警告(self):
        screen = noise(1080, 1920, 21)
        crop = screen[100:200, 100:300]          # 200x100，比车卡小得多
        level, tip = crop_quality(crop, screen)
        self.assertEqual(level, "warn")
        self.assertIn("偏小", tip)

    def test_框到空白会警告(self):
        screen = noise(1080, 1920, 22)
        blank = np.full((360, 620), 30, np.uint8)   # 纯色区域
        screen[300:660, 600:1220] = blank
        crop = screen[300:660, 600:1220]
        level, tip = crop_quality(crop, screen)
        self.assertEqual(level, "warn")
        self.assertIn("没有内容", tip)

    def test_框到到处都是的界面元素会警告(self):
        screen = noise(1080, 1920, 23)
        tile = noise(360, 620, 24)               # 车卡尺寸，但是个「通用元素」
        # 同一个图案在画面上出现两次（模拟通用的边框/分隔线/背景花纹）
        for x in (100, 1250):
            screen[300:660, x:x + 620] = tile
        crop = screen[300:660, 100:720].copy()
        level, tip = crop_quality(crop, screen)
        self.assertEqual(level, "warn")
        self.assertIn("匹到别处", tip)

    def test_正常的车卡能通过(self):
        screen = noise(1080, 1920, 25)
        # 一块 620x360 的「车卡」：有内容、只此一处
        card = noise(360, 620, 26)
        screen[400:760, 600:1220] = card
        crop = screen[400:760, 600:1220].copy()
        level, tip = crop_quality(crop, screen)
        self.assertEqual(level, "ok", f"正常车卡不该报警：{tip}")

    def test_不传整屏也能用(self):
        card = noise(360, 620, 27)
        level, tip = crop_quality(card, None)
        self.assertEqual(level, "ok", tip)

    def test_空图不崩(self):
        level, tip = crop_quality(np.zeros((0, 0, 3), np.uint8), None)
        self.assertEqual(level, "warn")


if __name__ == "__main__":
    unittest.main()
