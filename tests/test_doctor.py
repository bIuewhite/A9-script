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
