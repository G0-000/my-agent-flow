"""一、文件说明
    反射解析：配置里只存 "module:attr" 字符串，运行时再 import，避免启动即加载所有模型 SDK。
    典型用途：provider 配置写 langchain_openai:ChatOpenAI，用到时才导入。

二、目录结构
    packages/harness/myagentflow/reflection/
    ├── __init__.py
    └── resolvers.py ← 本文件

三、关键方法
    resolve_variable()  "a.b:c" -> 对象，可校验类型。
    resolve_class()     额外要求是类 / 是某基类子类。
"""

from __future__ import annotations

from importlib import import_module
from typing import TypeVar

MODULE_TO_PACKAGE_HINTS = {
    "langchain_google_genai": "langchain-google-genai",
    "langchain_anthropic": "langchain-anthropic",
    "langchain_openai": "langchain-openai",
    "langchain_deepseek": "langchain-deepseek",
}


def _build_missing_dependency_hint(module_path: str, err: ImportError) -> str:
    """缺依赖时给出可执行的安装提示。"""
    module_root = module_path.split(".", 1)[0]
    missing_module = getattr(err, "name", None) or module_root
    package_name = MODULE_TO_PACKAGE_HINTS.get(
        module_root
    ) or MODULE_TO_PACKAGE_HINTS.get(missing_module, missing_module.replace("_", "-"))
    return f"Missing dependency '{missing_module}'. Install it with `uv add {package_name}`."


T = TypeVar("T")


def resolve_variable(
    variable_path: str,
    expected_type: type | tuple[type, ...] | None = None,
):
    """解析 "module:attr"；模块不存在/属性不存在都统一抛 ImportError。"""
    try:
        module_path, variable_name = variable_path.rsplit(":", 1)
    except ValueError as err:
        raise ImportError(
            f"{variable_path} doesn't look like a variable path. Example: pkg.module:variable"
        ) from err
    try:
        module = import_module(module_path)
    except ImportError as err:
        module_root = module_path.split(".", 1)[0]
        if (
            isinstance(err, ModuleNotFoundError)
            or getattr(err, "name", None) == module_root
        ):
            raise ImportError(
                f"Could not import module {module_path}. {_build_missing_dependency_hint(module_path, err)}"
            ) from err
        raise ImportError(f"Error importing module {module_path}: {err}") from err
    try:
        variable = getattr(module, variable_name)
    except AttributeError as err:
        raise ImportError(
            f"Module {module_path} does not define {variable_name}"
        ) from err
    if expected_type is not None and not isinstance(variable, expected_type):
        type_name = (
            expected_type.__name__
            if isinstance(expected_type, type)
            else " or ".join(t.__name__ for t in expected_type)
        )
        raise ValueError(
            f"{variable_path} is not an instance of {type_name}, got {type(variable).__name__}"
        )
    return variable


def resolve_class(class_path: str, base_class: type | None = None) -> type:
    """解析类；可选校验继承关系。"""
    model_class = resolve_variable(class_path, expected_type=type)
    if not isinstance(model_class, type):
        raise ValueError(f"{class_path} is not a valid class")  # noqa: TRY004
    if base_class is not None and not issubclass(model_class, base_class):
        raise ValueError(f"{class_path} is not a subclass of {base_class.__name__}")
    return model_class
