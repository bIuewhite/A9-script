# -*- coding: utf-8 -*-
"""版本号相关的一致性测试。

版本号只写在 version.py 里，其它地方（README、CHANGELOG）必须跟着写一致；
这些测试就是防止「改了 version.py 忘了改文档」或者格式写乱。
"""
import os
import re
import unittest

import version
from tests import PROJECT_ROOT


class VersionTest(unittest.TestCase):
    def test_版本号格式是语义化版本(self):
        self.assertRegex(version.__version__, r"^\d+\.\d+\.\d+$",
                         "版本号应该形如 1.0.0（major.minor.patch）")

    def test_发版日期格式(self):
        self.assertRegex(version.__release_date__, r"^\d{4}-\d{2}-\d{2}$")

    def test_展示文本跟版本号一致(self):
        self.assertEqual(version.VERSION_TEXT, "v" + version.__version__)

    def test_changelog里有当前版本(self):
        path = os.path.join(PROJECT_ROOT, "CHANGELOG.md")
        self.assertTrue(os.path.exists(path), "缺少 CHANGELOG.md")
        with open(path, encoding="utf-8") as f:
            text = f.read()
        self.assertIn(f"v{version.__version__}", text,
                      "改了 version.py 的版本号，也要在 CHANGELOG.md 顶部加一段")

    def test_readme里有当前版本(self):
        path = os.path.join(PROJECT_ROOT, "README.md")
        self.assertTrue(os.path.exists(path), "缺少 README.md")
        with open(path, encoding="utf-8") as f:
            text = f.read()
        self.assertIn(version.__version__, text,
                      "README 里的版本号（徽章/说明）要跟 version.py 保持一致")

    def test_界面和日志都从version取版本号(self):
        """不许在别处把版本号写死 —— 否则迟早对不上。"""
        for fname in ("gui.py", "bot.py", "main.py"):
            path = os.path.join(PROJECT_ROOT, fname)
            with open(path, encoding="utf-8") as f:
                text = f.read()
            self.assertIn("VERSION_TEXT", text, f"{fname} 应该使用 version.VERSION_TEXT")

    def test_没有把版本号硬编码在别处(self):
        """不许在别处把版本号写死 —— 否则迟早对不上。

        只扫项目根目录的 .py（界面/日志最可能出现硬编码的地方）。
        不扫 .bat / .cs：那些是构建脚本，里面本来就有 .NET 的
        v4.0.30319 之类版本号，会误报。
        """
        pat = re.compile(r"(?<![\w.\\])\d+\.\d+\.\d+")
        for fname in os.listdir(PROJECT_ROOT):
            if not fname.endswith(".py") or fname == "version.py":
                continue
            path = os.path.join(PROJECT_ROOT, fname)
            with open(path, encoding="utf-8", errors="ignore") as f:
                for i, line in enumerate(f, 1):
                    if pat.search(line):
                        self.fail(f"{fname}:{i} 里写死了版本号，请改用 version.VERSION_TEXT\n"
                                  f"    {line.strip()}")


if __name__ == "__main__":
    unittest.main()
