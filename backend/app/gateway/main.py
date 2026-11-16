"""网关入口：只做装配，不写业务。

为什么健康检查要碰一下 checkpointer：
进程活着但数据库打不开是最常见的「假健康」，
只看 200 会让负载均衡一直往这台机器派活。
"""
from __future__ import annotations

from fastapi import FastAPI


def create_app() -> FastAPI:
    from app.gateway.routers.chat import router as chat_router

    app = FastAPI(title="my-agent-flow")
    app.include_router(chat_router, prefix="/api")

    @app.get("/health")
    def health() -> dict[str, str]:
        from myagentflow.agents.checkpointer.provider import get_checkpointer

        try:
            get_checkpointer()
            db = "ok"
        except Exception as exc:          # 数据库打不开：不是健康
            db = f"error: {exc}"
        return {"status": "ok" if db == "ok" else "degraded", "checkpointer": db}

    return app


app = create_app()
