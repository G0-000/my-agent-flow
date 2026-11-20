"""一、文件说明
    管理面/服务层共用的错误类型；service 抛这些异常，路由层统一转 HTTP 状态码。

二、目录结构
    packages/harness/myagentflow/admin/errors.py（本文件）

三、关键方法
    AdminError 基类；NotFoundError -> 404，ValidationError -> 400。
"""

from __future__ import annotations


class AdminError(Exception):
    """管理面错误基类，带 code / message。"""

    code = "admin_error"

    def __init__(self, message: str = "", *, code: str | None = None) -> None:
        super().__init__(message or self.code)
        self.message = message or self.code
        if code:
            self.code = code


class NotFoundError(AdminError):
    code = "not_found"


class ValidationError(AdminError):
    code = "validation_error"
