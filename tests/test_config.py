# -*- coding: utf-8 -*-
"""配置与参数读写的一致性测试（离线，不碰模拟器）。

主要盯住：
  · 车辆识别阈值必须比通用阈值更严（这是「选错车」修复的核心）
  · 模板注册表、必采清单、阈值覆盖表三者不能对不上
  · settings.json 是「合并写入」，改一个参数不能把别的参数冲掉
"""
import json
import os
import unittest

import config
from settings_io import SETTINGS_SCHEMA, _coerce, save_settings
from tests import cleanup, ensure_tmp_root


class ConfigSanityTest(unittest.TestCase):
    def test_adb路径不为空(self):
        self.assertIsInstance(config.ADB_PATH, str)
        self.assertTrue(config.ADB_PATH.strip(), "至少要给个 'adb' 兜底")

    def test_车辆阈值比通用阈值更严(self):
        # 车卡模板里有大片「所有车都一样」的装饰，实测别的车能匹到 0.83。
        # 所以车辆必须用更严的阈值，否则目标车不在画面时会点到别的车。
        self.assertGreater(config.CAR_MATCH_THRESHOLD, config.MATCH_THRESHOLD)
        self.assertGreaterEqual(config.CAR_MATCH_MIN_MARGIN, 0)

    def test_必采模板都在注册表里(self):
        for key in config.REQUIRED_TEMPLATES:
            self.assertIn(key, config.TEMPLATES, f"{key} 在必采清单里，但没在 TEMPLATES 注册")

    def test_模板文件名不重复(self):
        names = [fn for fn, _ in config.TEMPLATES.values()]
        self.assertEqual(len(names), len(set(names)), "有两个模板指向同一个文件")

    def test_模板注册表每项格式正确(self):
        for key, val in config.TEMPLATES.items():
            self.assertIsInstance(val, tuple, f"{key} 的格式应该是 (文件名, 说明)")
            self.assertEqual(len(val), 2, f"{key} 应该是 (文件名, 说明) 两项")
            fname, desc = val
            self.assertTrue(fname.endswith(".png"), f"{key} 的模板应该是 png")
            self.assertTrue(str(desc).strip(), f"{key} 缺少说明")

    def test_阈值覆盖表里的名字都真实存在(self):
        for key in config.TEMPLATE_THRESHOLDS:
            self.assertIn(key, config.TEMPLATES, f"阈值覆盖表里的 {key} 没有对应模板")

    def test_界面识别标志已注册(self):
        # 「从任意界面接着跑」依赖这两个标志
        for key in ("car_list", "mode_card"):
            self.assertIn(key, config.TEMPLATES)

    def test_等静止参数合理(self):
        self.assertGreater(config.CAR_SETTLE_TOL, 0)
        self.assertGreaterEqual(config.CAR_SETTLE_CHECKS, 2,
                                "只查 1 帧判断不出「画面在动」")
        self.assertGreater(config.CAR_SETTLE_INTERVAL_S, 0)
        self.assertGreater(config.CAR_SETTLE_TIMEOUT_S, config.CAR_SETTLE_INTERVAL_S)

    def test_氮气双击间隔合理(self):
        self.assertLess(config.NITRO_GAP_MIN_MS, config.NITRO_GAP_MAX_MS)
        self.assertGreater(config.NITRO_INTERVAL_S, 0)

    def test_参数设置页面里的键都真实存在(self):
        for item in SETTINGS_SCHEMA:
            self.assertTrue(hasattr(config, item["key"]),
                            f"参数设置里的 {item['key']} 在 config.py 里不存在")


class CoerceTest(unittest.TestCase):
    def test_坐标解析(self):
        coord = {"key": "X", "type": "coord"}
        self.assertEqual(_coerce(coord, "12,34"), (12, 34))
        self.assertEqual(_coerce(coord, "12，34"), (12, 34), "中文逗号也要认")
        self.assertEqual(_coerce(coord, " 12 , 34 "), (12, 34))
        self.assertIsNone(_coerce(coord, ""))
        self.assertIsNone(_coerce(coord, None))
        self.assertIsNone(_coerce(coord, "只有一个数"))

    def test_整数与浮点(self):
        self.assertEqual(_coerce({"type": "int"}, "18"), 18)
        self.assertEqual(_coerce({"type": "int"}, "18.7"), 18)
        self.assertEqual(_coerce({"type": "float"}, "0.92"), 0.92)

    def test_列表解析(self):
        self.assertEqual(_coerce({"type": "list"}, ["car_1", " car_2 "]),
                         ["car_1", "car_2"])
        self.assertEqual(_coerce({"type": "list"}, "car_1\ncar_2"), ["car_1", "car_2"])

    def test_下拉选择只接受列出的值(self):
        item = {"type": "choice",
                "options": [("auto", "自动选"), ("manual", "弹窗提醒我选")]}
        self.assertEqual(_coerce(item, "auto"), "auto")
        self.assertEqual(_coerce(item, "manual"), "manual")
        self.assertEqual(_coerce(item, " manual "), "manual")
        # 写错/写别的 → 退回第一项，别让配置里出现无效值
        self.assertEqual(_coerce(item, "乱写的"), "auto")
        self.assertEqual(_coerce(item, ""), "auto")


class SettingsMergeTest(unittest.TestCase):
    """settings.json 必须是「合并写入」，不能把用户其它设置冲掉。"""

    def setUp(self):
        self._old_base = config.BASE_DIR
        self._old_vals = {k: getattr(config, k, None) for k in ("NITRO_X", "NITRO_Y")}
        config.BASE_DIR = ensure_tmp_root()
        self.path = os.path.join(config.BASE_DIR, "settings.json")
        if os.path.exists(self.path):
            os.remove(self.path)

    def tearDown(self):
        config.BASE_DIR = self._old_base
        for k, v in self._old_vals.items():
            setattr(config, k, v)
        cleanup()

    def _read(self):
        with open(self.path, "r", encoding="utf-8") as f:
            return json.load(f)

    def test_只改一个参数不会冲掉别的(self):
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump({"NITRO_X": 111, "NITRO_Y": 222, "我的自定义键": "别删我"},
                      f, ensure_ascii=False)

        save_settings({"NITRO_Y": 999})
        data = self._read()

        self.assertEqual(data["NITRO_X"], 111, "没改的参数必须原样保留")
        self.assertEqual(data["NITRO_Y"], 999, "改了的参数要生效")
        self.assertEqual(data["我的自定义键"], "别删我", "不认识的自定义键也要保留")

    def test_schema外的键不会写进去(self):
        save_settings({"这个键不在schema里": 123})
        self.assertNotIn("这个键不在schema里", self._read())


class GamePackageTest(unittest.TestCase):
    """渠道服包名识别（纯逻辑）——4399 / 华为 / 小米 / 国际服都要认出来。"""

    PM = """package:com.android.settings
package:com.aligames.kuang.kybc.4399
package:com.tencent.mm
package:com.gameloft.android.ANMP.GloftA9HM
"""

    def test_认出渠道服和国际服(self):
        found = config.guess_game_package(self.PM)
        self.assertEqual(found, ["com.aligames.kuang.kybc.4399",
                                 "com.gameloft.android.ANMP.GloftA9HM"])
        self.assertNotIn("com.android.settings", found)
        self.assertNotIn("com.tencent.mm", found)

    def test_空输入返回空(self):
        self.assertEqual(config.guess_game_package(""), [])
        self.assertEqual(config.guess_game_package(None), [])

    def test_候选去重且保序(self):
        self.assertEqual(config.guess_game_package("package:b.kuang.x\npackage:a.kuang.y\n"),
                         ["b.kuang.x", "a.kuang.y"])

    def test_优先级_前台最优先(self):
        cands = ["a.kuang.x", "b.kuang.y"]
        self.assertEqual(config.pick_game_package(cands, "a.kuang.x", foreground="b.kuang.y"),
                         "b.kuang.y", "正在前台的那个最准")

    def test_优先级_只有一个进程活着就用它(self):
        cands = ["a.kuang.x", "b.kuang.y"]
        self.assertEqual(config.pick_game_package(cands, "", running=["b.kuang.y"]),
                         "b.kuang.y")

    def test_优先级_再退到配置值(self):
        cands = ["com.aligames.kuang.kybc.tap", "com.gameloft.x"]
        self.assertEqual(config.pick_game_package(cands, "com.gameloft.x"),
                         "com.gameloft.x")

    def test_优先级_最后退到国服前缀(self):
        cands = ["com.gameloft.x", "com.aligames.kuang.kybc.4399"]
        self.assertEqual(config.pick_game_package(cands, ""),
                         "com.aligames.kuang.kybc.4399")

    def test_没有候选就返回空(self):
        self.assertEqual(config.pick_game_package([], "com.x"), "")
        self.assertEqual(config.pick_game_package(None, "com.x"), "")

    def test_解析Activity(self):
        self.assertEqual(
            config.guess_activity("priority=0\ncom.a.b/com.epicgames.ue4.GameActivity"),
            "com.a.b/com.epicgames.ue4.GameActivity")
        self.assertEqual(config.guess_activity(""), "")
        self.assertEqual(config.guess_activity("没有斜杠"), "")


if __name__ == "__main__":
    unittest.main()
