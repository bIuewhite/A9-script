# -*- coding: utf-8 -*-
"""批处理文件的格式检查。

为什么要专门测这个：`.bat` 有几条很容易踩、而且踩了很难查的规矩 ——

1. 必须是 CRLF 换行。纯 LF 的 bat 在 cmd 里会被解析乱掉（症状是莫名其妙的
   "xxx is not recognized as an internal or external command"）。
2. 不能出现非 ASCII 字符（中文）。cmd 用【启动时的代码页】解析整个文件
   （中文系统是 936），文件里写 `chcp 65001` 也来不及生效 —— UTF-8 的中文
   会被按 GBK 解码，把后面的字符一起吃掉。

所以本项目的约定是：**bat 只写 ASCII 命令，中文提示一律交给 Python 打印**
（Python 走 Windows 控制台 API，任何代码页都正常）。
"""
import os
import unittest

from tests import PROJECT_ROOT


def bat_files():
    return sorted(f for f in os.listdir(PROJECT_ROOT) if f.lower().endswith(".bat"))


class BatFileTest(unittest.TestCase):
    def test_至少有一个bat(self):
        self.assertTrue(bat_files(), "项目里应该有 bat 文件")

    def test_全部用CRLF换行(self):
        for name in bat_files():
            with open(os.path.join(PROJECT_ROOT, name), "rb") as f:
                data = f.read()
            lf_only = data.count(b"\n") - data.count(b"\r\n")
            self.assertEqual(lf_only, 0,
                             f"{name} 有 {lf_only} 处纯 LF 换行；"
                             f"bat 必须用 CRLF，否则 cmd 解析会出错")

    def test_不含非ASCII字符(self):
        for name in bat_files():
            with open(os.path.join(PROJECT_ROOT, name), "rb") as f:
                data = f.read()
            bad = [(i, b) for i, b in enumerate(data) if b > 127]
            if bad:
                pos, byte = bad[0]
                line = data[:pos].count(b"\n") + 1
                self.fail(f"{name} 第 {line} 行有非 ASCII 字节 0x{byte:02x}；"
                          f"bat 里的中文会被 cmd 按系统代码页解码乱掉，"
                          f"中文提示请交给 Python 打印")

    def test_不含BOM(self):
        for name in bat_files():
            with open(os.path.join(PROJECT_ROOT, name), "rb") as f:
                self.assertNotEqual(f.read(3), b"\xef\xbb\xbf",
                                    f"{name} 带了 BOM，老版 cmd 会把首行命令弄坏")

    def test_都能被cmd当成命令处理(self):
        """抽查内容：第一个有效行应该是 @echo off 或 rem。"""
        for name in bat_files():
            with open(os.path.join(PROJECT_ROOT, name), encoding="ascii") as f:
                first = f.readline().strip().lower()
            self.assertTrue(first.startswith("@echo off") or first.startswith("rem"),
                            f"{name} 第一行是 {first!r}，建议以 @echo off 开头")


if __name__ == "__main__":
    unittest.main()
