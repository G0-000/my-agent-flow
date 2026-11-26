"""一、文件说明
    篇级演示脚本（scripts/ch01–ch05）冒烟测试：子进程逐个运行，断言退出码 0 且首行前缀正确。

二、覆盖
    test_demo_script_runs[param]  ch01_model_smoke 首行 echo:（stub 回显）；ch01_agent_loop 与 ch02–05 首行 OK:。

三、运行
    uv run pytest tests/chapters/test_demos.py -q
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = BACKEND_DIR / "scripts"

# (脚本名, 首行前缀)。ch01_model_smoke 只验证 create_chat_model().invoke() 链路，
# 首行是 stub 回显的 echo:；其余脚本自带离线替身模型，自检通过后首行打印 OK:。
CASES = [
    ("ch01_model_smoke.py", "echo:"),
    ("ch01_agent_loop.py", "OK:"),
    ("ch02_context_demo.py", "OK:"),
    ("ch03_tool_demo.py", "OK:"),
    ("ch04_checkpoint_demo.py", "OK:"),
    ("ch05_memory_demo.py", "OK:"),
]

# 只含 stub provider 的离线配置：测试自给自足，不依赖本机 config.local.yaml。
STUB_CONFIG = """\
log_level: info
primary_model: local
models:
  - name: local
    vendor: stub
    use: myagentflow.models.providers.stub:StubChatModel
    model: stub
    temperature: 0.0
checkpointer:
  type: memory
storage:
  backend: sqlite
  sqlite_path: data/app/test.sqlite
"""


@pytest.mark.parametrize(("script_name", "prefix"), CASES)
def test_demo_script_runs(script_name: str, prefix: str, tmp_path: Path) -> None:
    """子进程运行演示脚本：退出码 0，且首行以约定前缀开头。"""
    config_path = tmp_path / "config.yaml"
    config_path.write_text(STUB_CONFIG, encoding="utf-8")

    env = os.environ.copy()
    env["MYAGENTFLOW_CONFIG_PATH"] = str(config_path)
    proc = subprocess.run(
        [sys.executable, str(SCRIPTS_DIR / script_name)],
        check=False,
        cwd=BACKEND_DIR,
        env=env,
        input="你好\n",
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.returncode == 0, f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
    first_line = proc.stdout.splitlines()[0] if proc.stdout.splitlines() else ""
    assert first_line.startswith(prefix), f"首行={first_line!r} 期望前缀={prefix!r}"
