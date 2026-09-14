# -*- coding: utf-8 -*-
"""环境体检（doctor.py）里纯逻辑的测试。

这些函数都是「输入文本 → 输出判断」，不需要模拟器、不需要装东西。
将来改判据（比如支持别的分辨率）时，有测试兜着。
"""
import unittest

import doctor


class VersionTest(unittest.TestCase):
    def test_版本字符串转元组(self):
        self.assertEqual(doctor.version_tuple("3.14.6"), (3, 14, 6))
        self.assertEqual(doctor.version_tuple("3.12.0rc1"), (3, 12, 0))
        self.assertEqual(doctor.version_tuple("4.8"), (4, 8))
        self.assertEqual(doctor.version_tuple(""), ())
        self.assertEqual(doctor.version_tuple("abc"), ())

    def test_Python版本判据(self):
        ok, msg = doctor.check_python((3, 14, 6))
        self.assertTrue(ok, msg)
        ok, msg = doctor.check_python((3, 10, 0))
        self.assertTrue(ok, msg)
        ok, msg = doctor.check_python((3, 9, 18))
        self.assertFalse(ok, "3.9 应该判为太旧")
        self.assertIn("3.10", msg)
        ok, _ = doctor.check_python((2, 7, 18))
        self.assertFalse(ok)


class WmSizeTest(unittest.TestCase):
    def test_解析分辨率(self):
        self.assertEqual(doctor.parse_wm_size("Physical size: 1920x1080"), (1920, 1080))
        self.assertEqual(
            doctor.parse_wm_size("Physical size: 1080x1920\nOverride size: 1920x1080"),
            (1920, 1080), "有 Override 时应该以 Override 为准（那才是实际生效的）")
        self.assertIsNone(doctor.parse_wm_size(""))
        self.assertIsNone(doctor.parse_wm_size("no size here"))

    def test_分辨率判据(self):
        state, msg, _ = doctor.check_resolution((1920, 1080))
        self.assertEqual(state, "ok")
        state, msg, hint = doctor.check_resolution((1080, 1920))
        self.assertEqual(state, "bad")
        self.assertIn("竖屏", msg)
        self.assertTrue(hint)
        state, _, _ = doctor.check_resolution((1280, 720))
        self.assertEqual(state, "bad")
        state, _, hint = doctor.check_resolution(None)
        self.assertEqual(state, "warn")
        self.assertTrue(hint)
        # 1080x1920 和 1920x1080 都是 16:9，必须区分开
        self.assertNotEqual(doctor.check_resolution((1920, 1080))[0],
                           doctor.check_resolution((1080, 1920))[0])


class AdbDeviceTest(unittest.TestCase):
    """体检调 adb 时必须指定设备（-s）。

    不然同时开着两个模拟器（雷电 + MuMu 之类）时，adb 会报
    "more than one device/emulator"，分辨率和游戏安装检查会全部失败，
    看起来像"游戏没装"，实际是没指定设备。
    """

    def _capture(self, *args, **kw):
        import subprocess

        seen = []
        real = subprocess.run

        class Fake:
            returncode = 0
            stdout = b"Physical size: 1920x1080\n"

        def fake(cmd, **kw2):
            seen.append(list(cmd))
            return Fake()

        subprocess.run = fake
        try:
            doctor._run_adb(*args, **kw)
        finally:
            subprocess.run = real
        return seen[0]

    def test_查分辨率和装包要带设备(self):
        import config
        cmd = self._capture(["shell", "wm", "size"])
        self.assertIn("-s", cmd, "体检必须用 -s 指定设备")
        self.assertIn(config.DEVICE_SERIAL, cmd)
        cmd = self._capture(["shell", "pm", "list", "packages", "com.x"])
        self.assertIn("-s", cmd)

    def test_列设备和服务管理不能带设备(self):
        # adb devices 要列出所有设备；kill-server 之类的也不能带 -s
        for args in (["devices"], ["kill-server"], ["start-server"]):
            cmd = self._capture(args, use_serial=False)
            self.assertNotIn("-s", cmd, f"{args[0]} 不该带 -s")

    def test_设备序列号为空时不加_s(self):
        import config
        old = config.DEVICE_SERIAL
        config.DEVICE_SERIAL = ""
        try:
            cmd = self._capture(["shell", "wm", "size"])
        finally:
            config.DEVICE_SERIAL = old
        self.assertNotIn("-s", cmd)


class GuessPackageTest(unittest.TestCase):
    """渠道服包名识别（4399 / 华为 / 小米 等）——用户不用自己去翻包名。"""

    PM = """package:com.android.settings
package:com.aligames.kuang.kybc.4399
package:com.tencent.mm
package:com.gameloft.android.ANMP.GloftA9HM
"""

    def test_能认出4399渠道服(self):
        found = doctor.guess_game_package(self.PM)
        self.assertIn("com.aligames.kuang.kybc.4399", found)
        self.assertIn("com.gameloft.android.ANMP.GloftA9HM", found, "国际服也要认出来")
        self.assertNotIn("com.android.settings", found)
        self.assertNotIn("com.tencent.mm", found)

    def test_返回顺序和去重(self):
        found = doctor.guess_game_package(
            "package:b.kuang.x\npackage:a.kuang.y\npackage:b.kuang.x\n")
        self.assertEqual(found, ["b.kuang.x", "a.kuang.y"])

    def test_空输入不炸(self):
        self.assertEqual(doctor.guess_game_package(""), [])
        self.assertEqual(doctor.guess_game_package(None), [])

    def test_解析Activity(self):
        self.assertEqual(
            doctor.guess_activity("priority=0\ncom.aligames.kuang.kybc.4399/com.epicgames.ue4.GameActivity"),
            "com.aligames.kuang.kybc.4399/com.epicgames.ue4.GameActivity")
        self.assertEqual(doctor.guess_activity(""), "")
        self.assertEqual(doctor.guess_activity("no activity here"), "")


class DepsTest(unittest.TestCase):
    def test_依赖齐全时全过(self):
        rows = doctor.check_deps(get_module=lambda name: "9.9.9")
        for name, ok, ver in rows:
            self.assertTrue(ok, f"{name} 应该判为正常")
        self.assertEqual([r[0] for r in rows], ["cv2", "numpy", "tkinter"])

    def test_缺依赖时能报出来(self):
        def fake(name):
            if name == "cv2":
                raise ImportError("No module named 'cv2'")
            return "1.0"

        rows = dict((n, (ok, v)) for n, ok, v in doctor.check_deps(get_module=fake))
        self.assertFalse(rows["cv2"][0])
        self.assertIn("cv2", rows["cv2"][1])
        self.assertTrue(rows["numpy"][0])


class TemplateTest(unittest.TestCase):
    def test_缺模板能列出来(self):
        miss_btn, miss_car = doctor.missing_templates(exists=lambda fname: False)
        self.assertTrue(miss_btn, "全都标成不存在时，应该报出缺的按钮模板")
        self.assertIn("car_1.png", [c + ".png" for c in miss_car])

        miss_btn2, miss_car2 = doctor.missing_templates(exists=lambda fname: True)
        self.assertEqual(miss_btn2, [])
        self.assertEqual(miss_car2, [])


if __name__ == "__main__":
    unittest.main()
