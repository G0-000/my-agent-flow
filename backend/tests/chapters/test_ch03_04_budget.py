"""一、文件说明
    03/04 上下文控制：压缩阈值、内联截断、超大结果落盘。

二、覆盖
    test_cap_beats_ratio()   大窗口被绝对上限截住，小窗口按比例算。
    test_refill()            回填目标小于阈值，同轮回填比跨轮更保守。
    test_truncate_middle()   超预算时保留头尾、中间出现省略标记，且 token 不超预算。
    test_persist_large()     超阈值落盘并返回信封，小结果原样返回。

三、运行
    uv run pytest tests/chapters/test_ch03_04_budget.py -q
"""

from __future__ import annotations


def test_cap_beats_ratio():
    """大窗口被绝对上限截住，小窗口按比例算。"""
    from myagentflow.context.budget import ABSOLUTE_CAP, compact_threshold

    assert compact_threshold(256_000) == ABSOLUTE_CAP
    assert compact_threshold(100_000) == 90_000  # 小窗口时比例生效


def test_refill():
    """回填目标小于阈值，同轮回填比跨轮更保守。"""
    from myagentflow.context.budget import refill_target

    assert refill_target(150_000) < 150_000
    assert refill_target(150_000, same_turn=True) < refill_target(150_000)


def test_truncate_middle():
    """超预算时保留头尾、中间出现省略标记，且 token 不超预算。"""
    from myagentflow.context.tool_tokens import count_tool_tokens
    from myagentflow.tools.tool_output_truncation import (
        formatted_truncate_tool_output,
        truncate_text_to_token_budget,
    )

    text = "HEAD\n" + "x" * 20_000 + "\nTAIL"
    out = truncate_text_to_token_budget(text, 200)
    assert out.startswith("HEAD")
    assert out.endswith("TAIL")
    assert "tokens truncated" in out
    assert count_tool_tokens(out) <= 200

    formatted = formatted_truncate_tool_output(text, 200)
    assert formatted.startswith("Warning: truncated output")
    assert "Total output lines:" in formatted


def test_persist_large(monkeypatch, tmp_path):
    """超阈值落盘并返回信封，小结果原样返回。"""
    from myagentflow.tools import large_result_store as store

    monkeypatch.setenv("MYAF_DATA_DIR", str(tmp_path))
    content = "line\n" * 4_000  # 20K 字符，超过 10K 阈值
    envelope = store.maybe_persist(content, "bash", "call-1")
    assert store.is_persisted_output_content(envelope)
    assert "<persisted-output>" in envelope and "</persisted-output>" in envelope
    assert str(tmp_path / "large_tool_results") in envelope

    files = list((tmp_path / "large_tool_results").iterdir())
    assert len(files) == 1
    assert files[0].read_text(encoding="utf-8") == content

    assert store.maybe_persist("small", "bash", "call-2") == "small"
