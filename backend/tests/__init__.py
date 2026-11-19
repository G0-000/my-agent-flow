"""测试包：让 `tests.chapters.helpers_jwt` 这类跨文件导入成立。

没有这个文件时，`tests` 不是一个包，`test_ch11_02_jwt.py` 里的
`from tests.chapters.helpers_jwt import make_token` 会 ModuleNotFoundError。
"""
