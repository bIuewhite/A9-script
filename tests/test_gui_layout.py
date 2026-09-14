# -*- coding: utf-8 -*-
"""界面布局的两条「防复发」检查（只读源码，不启动 Tk，所以 CI 上也能跑）。

背景：参数页右侧内容曾经看不见 —— 画布里的内嵌 frame 没钉住宽度，
它按内容自然宽度显示（实测 1415px），而画布只有 1276px，
右边 139px 被裁掉，又没有横向滚动条，用户永远够不着。
"""
import os
import re
import unittest

from tests import PROJECT_ROOT

GUI = os.path.join(PROJECT_ROOT, "gui.py")


def read_gui():
    with open(GUI, encoding="utf-8") as f:
        return f.read()


def body_of(text, func_name):
    """粗略截出某个方法的源码（从 def 到下一个同级 def）。"""
    m = re.search(r"\n    def %s\(" % re.escape(func_name), text)
    if not m:
        return ""
    rest = text[m.end():]
    nxt = re.search(r"\n    def ", rest)
    return rest[:nxt.start()] if nxt else rest


class ScrollAreaTest(unittest.TestCase):
    def test_内嵌窗口钉住了宽度(self):
        body = body_of(read_gui(), "_scroll_area")
        self.assertTrue(body, "gui.py 里找不到 _scroll_area")
        self.assertRegex(body, r"itemconfigure\(\s*win\s*,\s*width",
                         "滚动区域必须把内嵌窗口的宽度钉成画布宽度，"
                         "否则内容比画布宽时右边会被裁掉且够不着")

    def test_滚轮没有在初始化时就bind_all(self):
        body = body_of(read_gui(), "_scroll_area")
        # bind_all 只能出现在 Enter 的回调里（进入这块区域才接管滚轮），
        # 不能一上来就 bind_all —— 那样最后一个绑定的画布会抢走所有页面的滚轮
        # （只匹配真正的调用 bind_all(，注释里提到不算）
        for line in body.splitlines():
            if re.search(r"\bbind_all\s*\(", line):
                self.assertIn("Enter", line,
                              f"这行 bind_all 不是在 <Enter> 里绑的：{line.strip()}")

    def test_两个滚动页都用同一个实现(self):
        text = read_gui()
        self.assertIn("self.p_canvas, self.p_inner = self._scroll_area", text,
                      "参数页应该用 _scroll_area")
        self.assertIn("self.car_canvas, self.car_inner = self._scroll_area", text,
                      "选车页应该用 _scroll_area（同样的坑）")
        self.assertNotIn("create_window((0, 0), window=self.p_inner", text,
                         "参数页里还留着老的 create_window 写法")

    def test_提示文字会换行(self):
        body = body_of(read_gui(), "load_settings")
        self.assertIn("wraplength", body,
                      "参数页的提示文字要设 wraplength，否则 3 列会被撑得比画布宽")


class RewardNoticeTest(unittest.TestCase):
    def test_跨线程只改标志不碰控件(self):
        """脚本线程不能直接操作 Tk 控件，必须只改标志、由主线程轮询时弹窗。"""
        text = read_gui()
        body = body_of(text, "set_reward_notice")
        self.assertTrue(body)
        self.assertNotIn("Toplevel", body, "set_reward_notice 里不该建窗口")
        self.assertIn("_sync_reward_popup", text, "缺少主线程里的同步逻辑")
        # poll_status 里要调用同步
        self.assertIn("self._sync_reward_popup()", body_of(text, "poll_status"))


if __name__ == "__main__":
    unittest.main()
