#!/usr/bin/env python3
# 第 05 篇最小闭环：新 thread 能召回旧偏好，并能注入 prompt。
# 旧 thread 写入一条偏好 → 新 thread 关键词召回并记录召回快照
# → format_atoms_block 生成 <memory> 注入块。结果写 tmp/ch05/recall.txt。

from __future__ import annotations

import os
import sys
from pathlib import Path

_OUT_DIR = Path(__file__).resolve().parents[1] / "tmp" / "ch05"
os.environ["MYAF_DATA_DIR"] = str(_OUT_DIR / "data")
os.environ["MYAF_MEMORY_DB"] = str(_OUT_DIR / "memory.sqlite")

from myagentflow.config.paths import reset_paths_cache
from myagentflow.memory import facade, recall_snapshot
from myagentflow.memory.namespaces import user_ns

PREFERENCE = "用户偏好简短的中文回答"
QUERY = "中文回答 偏好"
OLD_THREAD = "thread-old-demo"
NEW_THREAD = "thread-new-demo"


def main() -> int:
    reset_paths_cache()
    namespace = user_ns("demo-user")

    # 旧 thread：明确选出的事实写成长期记忆
    atom_id = facade.remember(
        namespace,
        PREFERENCE,
        kind="preference",
        subject_key="reply_style",
        importance=0.9,
        confidence=0.95,
        source="user",
    )
    if not atom_id:
        print("FAILED: remember returned None", file=sys.stderr)
        return 1

    # 新 thread：关键词召回 + 召回快照
    hits = facade.recall([namespace], QUERY, top_k=3)
    recall_snapshot.record_thread_recall(NEW_THREAD, query=QUERY, hits=hits)
    snapshot = recall_snapshot.get_thread_recall(NEW_THREAD)

    # 注入：格式化成 <memory> 块
    block = facade.format_atoms_block(hits)

    checks = {
        "remembered": atom_id is not None,
        "recalled_in_new_thread": bool(hits) and hits[0]["id"] == atom_id,
        "snapshot_recorded": bool(snapshot) and snapshot.get("hit_count", 0) >= 1,
        "injected_block": "<memory>" in block and PREFERENCE in block,
    }
    failed = [name for name, ok in checks.items() if not ok]
    if failed:
        print(f"FAILED: {failed}", file=sys.stderr)
        return 1

    lines = [
        f"OK: recalled=1 snapshot_hits={snapshot['hit_count']} injected=True",
        f"旧 thread：{OLD_THREAD} 写入偏好「{PREFERENCE}」(atom={atom_id})",
        f"新 thread：{NEW_THREAD} 用「{QUERY}」召回 {len(hits)} 条",
        f"注入块预览：{block[:160]}{'…' if len(block) > 160 else ''}",
    ]
    _OUT_DIR.mkdir(parents=True, exist_ok=True)
    (_OUT_DIR / "recall.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(lines[0])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
