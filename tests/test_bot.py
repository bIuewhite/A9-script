# -*- coding: utf-8 -*-
"""bot.py 里纯逻辑的测试（不需要模拟器）。

重点盯住「动态奖励」卡位坐标：卡片图案每次都换，所以只能按固定卡位点，
而实测有两种变体，几何还不一样 —— 这里用实测数据把「两种都能点中」钉死。
"""
import re
import unittest

import bot
import config

# 实测数据：两种变体的卡位范围（单位：像素，1920x1080）
#   赛后那种：顶栏可见、底部有『确认』按钮
#   活动那种：全屏遮罩、只有右上角 ×
VARIANTS = (
    ("赛后那种", [(80, 313), (425, 660), (771, 1005), (1117, 1351), (1462, 1697)],
     (457, 858)),
    ("活动那种", [(141, 382), (486, 727), (832, 1073), (1177, 1418), (1523, 1764)],
     (423, 707)),
)


class RewardCardTest(unittest.TestCase):
    def test_每个卡位都落在两种变体的卡片里(self):
        for name, xs, (y0, y1) in VARIANTS:
            for i, (a, b) in enumerate(xs, start=1):
                x, y = bot.reward_card_xy(i)
                self.assertTrue(a <= x <= b,
                                f"{name} 第 {i} 张卡范围是 {a}~{b}，"
                                f"脚本却点 x={x} —— 会点到卡片外面")
                self.assertTrue(y0 <= y <= y1,
                                f"{name} 的卡片纵向是 {y0}~{y1}，脚本点的 y={y} 不在里面")

    def test_间距和递增(self):
        xs = [bot.reward_card_xy(i)[0] for i in range(1, 6)]
        self.assertEqual(xs, sorted(xs), "从左到右应该递增")
        steps = [xs[i + 1] - xs[i] for i in range(len(xs) - 1)]
        self.assertTrue(all(s == config.REWARD_CARD_STEP for s in steps),
                        f"间距应该都等于 REWARD_CARD_STEP，实际 {steps}")
        self.assertEqual(len(set(bot.reward_card_xy(i)[1] for i in range(1, 6))), 1,
                         "5 张卡片应该在同一条水平线上")

    def test_索引超出范围会被夹住(self):
        top = config.REWARD_MAX_INDEX
        self.assertEqual(bot.reward_card_xy(0), bot.reward_card_xy(1))
        self.assertEqual(bot.reward_card_xy(-3), bot.reward_card_xy(1))
        self.assertEqual(bot.reward_card_xy(top + 1), bot.reward_card_xy(top),
                         "超出范围要夹到最大，而不是点到屏幕外")
        self.assertEqual(bot.reward_card_xy(999), bot.reward_card_xy(top))

    def test_最大索引在屏幕内(self):
        x, _ = bot.reward_card_xy(config.REWARD_MAX_INDEX)
        self.assertLess(x, 1920, "最后一个可点的卡位必须在屏幕里")
        nx, _ = bot.reward_card_xy(config.REWARD_MAX_INDEX + 1)
        self.assertEqual(nx, x)


class RewardConfigTest(unittest.TestCase):
    def test_模式取值合法(self):
        self.assertIn(str(config.REWARD_MODE).lower(), ("auto", "manual"))

    def test_默认选的张数在可点范围内(self):
        self.assertGreaterEqual(config.REWARD_PICK_INDEX, 1)
        self.assertLessEqual(config.REWARD_PICK_INDEX, config.REWARD_MAX_INDEX)

    def test_确认按钮坐标在屏幕里(self):
        x, y = config.REWARD_CONFIRM_XY
        self.assertTrue(0 < x < 1920 and 0 < y < 1080)

    def test_动态奖励模板已注册且是必采(self):
        self.assertIn("dynamic_reward", config.TEMPLATES)
        self.assertIn("dynamic_reward", config.REQUIRED_TEMPLATES)


class ScreenStateTest(unittest.TestCase):
    def test_状态名字不重复(self):
        names = [getattr(bot, n) for n in dir(bot) if n.startswith("S_")]
        self.assertEqual(len(names), len(set(names)), "有两个状态重名，识别会乱")

    def test_动态奖励状态存在(self):
        self.assertTrue(hasattr(bot, "S_REWARD"))

    def test_类里没有写死的状态字符串(self):
        """detect_screen 必须返回 S_* 常量，别到处写中文字面量。"""
        with open(bot.__file__, encoding="utf-8") as f:
            src = f.read()
        body = src[src.index("def detect_screen"):src.index("def wait_for_known_screen")]
        self.assertNotIn('return "', body, "detect_screen 里出现了写死的状态字符串")


if __name__ == "__main__":
    unittest.main()
