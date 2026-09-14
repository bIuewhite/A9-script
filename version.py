# -*- coding: utf-8 -*-
"""version.py —— 版本号（全局唯一出处）

只在这里改版本号；其它地方都从这里 import。
界面标题、启动日志、环境自检里的版本会跟着一起变，不会出现
「界面写 v1.0、日志写 v1.1」这种对不上的情况。

版本规则（语义化版本 major.minor.patch）：
    patch  修 bug，用法不变
    minor  加新功能，向后兼容
    major  不兼容的大改（例如配置项大改、必须重新采集模板）

发版三步：
    1. 改这里的 __version__（和 __release_date__）
    2. 在 CHANGELOG.md 顶部加一段
    3. git commit && git tag v<版本号> && git push --tags

tests/test_version.py 会检查「版本号格式」以及「CHANGELOG/README 里有没有
写上当前版本」，所以漏改会被测试拦下来。
"""

__version__ = "1.0.1"

# 发版日期
__release_date__ = "2026-09-14"

# 展示用文本（界面、日志统一用它）
VERSION_TEXT = "v" + __version__
