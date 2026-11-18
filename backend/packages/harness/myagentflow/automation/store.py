"""一、文件说明
    自动化：规则 + 执行历史。
    为什么执行前先写 running：进程被杀时，只看历史会以为「从没跑过」，
    先写一条 running 才能让「上次是否完成」可判断。

二、目录结构
    packages/harness/myagentflow/automation/
    ├── __init__.py
    ├── heartbeat.py  心跳：状态没变就别叫模型。
    ├── notify.py  通知投递：多渠道 + 去重 + 失败隔离。
    ├── scheduler.py  调度器：最小 cron + 重启补偿。
    └── store.py  ← 本文件

三、关键方法
    AutomationStore  自动化定义与运行记录的 SQLite 存储。
"""
from __future__ import annotations

import sqlite3
import time
import uuid
from pathlib import Path

# 自动化任务与每次运行记录：automations 存「什么时候跑什么」，runs 存「跑了几次、成没成」。
# 用 CREATE TABLE IF NOT EXISTS，进程重启时直接复用已有库，不需要迁移脚本。
_SCHEMA = """
CREATE TABLE IF NOT EXISTS automations (
    id TEXT PRIMARY KEY, name TEXT NOT NULL, cron TEXT NOT NULL,
    prompt TEXT NOT NULL, enabled INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS runs (
    id TEXT PRIMARY KEY, automation_id TEXT NOT NULL,
    status TEXT NOT NULL, started_at REAL NOT NULL, finished_at REAL
);
"""


class AutomationStore:
    """自动化定义与运行记录的 SQLite 存储。"""
    def __init__(self, db_path: str | Path):
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.executescript(_SCHEMA)

    def add(self, name: str, cron: str, prompt: str) -> str:
        ident = uuid.uuid4().hex[:8]
        self._conn.execute("INSERT INTO automations (id, name, cron, prompt) VALUES (?, ?, ?, ?)",
                           (ident, name, cron, prompt))
        self._conn.commit()
        return ident

    def enabled(self) -> list[dict]:
        rows = self._conn.execute("SELECT id, name, cron, prompt FROM automations WHERE enabled=1").fetchall()
        return [{"id": r[0], "name": r[1], "cron": r[2], "prompt": r[3]} for r in rows]

    def begin_run(self, automation_id: str) -> str:
        ident = uuid.uuid4().hex[:8]
        self._conn.execute("INSERT INTO runs VALUES (?, ?, ?, ?, NULL)",
                           (ident, automation_id, "running", time.time()))
        self._conn.commit()
        return ident

    def finish_run(self, run_id: str, status: str) -> None:
        self._conn.execute("UPDATE runs SET status=?, finished_at=? WHERE id=?",
                           (status, time.time(), run_id))
        self._conn.commit()
