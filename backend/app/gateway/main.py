"""网关入口：只做装配，不写业务。

为什么健康检查要碰一下 checkpointer：
进程活着但数据库打不开是最常见的「假健康」，
只看 200 会让负载均衡一直往这台机器派活。
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI


@asynccontextmanager
async def _lifespan(app: FastAPI):
    """进程级后台任务：记忆抽取 worker。

    放 lifespan 而不是模块导入时启动：导入发生在测试收集阶段，
    那时配置和临时库都还没准备好。
    """
    from myagentflow.memory.worker import start_worker, stop_worker

    def _model_factory():
        from myagentflow.models.factory import create_chat_model

        return create_chat_model()

    start_worker(_model_factory)
    try:
        yield
    finally:
        stop_worker()


def create_app() -> FastAPI:
    from app.gateway.routers.approvals import router as approvals_router
    from app.gateway.routers.channels import router as channels_router
    from app.gateway.routers.chat import router as chat_router
    from app.gateway.routers.cua import router as cua_router
    from app.gateway.routers.sessions import router as sessions_router
    from app.gateway.routers.shares import router as shares_router

    app = FastAPI(title="my-agent-flow", lifespan=_lifespan)
    app.include_router(chat_router, prefix="/api")
    app.include_router(sessions_router, prefix="/api")
    app.include_router(shares_router, prefix="/api")
    app.include_router(approvals_router, prefix="/api")
    app.include_router(cua_router, prefix="/api")
    app.include_router(channels_router, prefix="/api")

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
