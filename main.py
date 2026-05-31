"""FastAPI 入口 - 支持 Semantic Scholar + 知识库管理 + 用户审核"""

import asyncio
import logging

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sse_starlette.sse import EventSourceResponse

from paper_agent.models import BackToFrontData, StepName
from paper_agent.orchestrator import SimpleOrchestrator
from paper_agent.api.knowledge_api import router as knowledge_router

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(title="Paper-Agent", version="2.1.0")

# CORS 配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册知识库 API 路由
app.include_router(knowledge_router)

# 全局状态队列 & 当前审核 Future
state_queue = asyncio.Queue()
current_review_future: asyncio.Future = None


@app.get("/api/research")
async def research_stream(query: str, max_papers: int = 20):
    """
    论文调研 SSE 接口

    Args:
        query: 用户查询需求
        max_papers: 最大论文数量（默认 20）
    """
    async def event_generator():
        while True:
            state = await state_queue.get()
            yield {"data": state.model_dump_json()}

    # 先启动事件生成器
    event_source = EventSourceResponse(event_generator(), media_type="text/event-stream")

    # 初始化编排器
    orchestrator = SimpleOrchestrator(state_queue=state_queue)

    # 启动异步任务
    asyncio.create_task(orchestrator.run(user_request=query, max_papers=max_papers))

    return event_source


@app.post("/send_input")
async def send_user_input(input: str = None):
    """
    用户审核反馈接口

    前端审核检索条件后，通过此接口提交确认/修改结果。
    唤醒阻塞的 workflow 继续执行。
    """
    global current_review_future

    if input is None:
        raise HTTPException(status_code=400, detail="input 参数不能为空")

    if current_review_future and not current_review_future.done():
        current_review_future.set_result(input)
        logger.info(f"收到用户审核输入: {input[:200]}...")
        return {"status": "received", "message": "审核结果已接收"}
    else:
        raise HTTPException(
            status_code=400,
            detail="当前没有等待审核的请求，或审核已超时",
        )


@app.get("/api/health")
async def health_check():
    """健康检查"""
    return {"status": "ok", "version": "2.1.0"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
