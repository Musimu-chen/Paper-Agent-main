"""工作流编排器 - 支持语义学者搜索 + 用户审核 + 知识库检索"""

import logging
import asyncio
from typing import Optional

from paper_agent.models import (
    WorkflowState, BackToFrontData, StepName,
)
from paper_agent.chains.search_chain import SearchChain, SOURCE_SEMANTIC_SCHOLAR
from paper_agent.chains.reading_chain import ReadingChain
from paper_agent.chains.analysis_chain import AnalysisChain
from paper_agent.chains.writing_chain import WritingChain
from paper_agent.chains.report_chain import ReportChain

logger = logging.getLogger(__name__)


class SimpleOrchestrator:
    """
    工作流编排器

    流程: search -> (user_review) -> read -> analyze -> write -> report
    使用纯 async/await 顺序编排，不依赖 LangGraph / AutoGen
    """

    def __init__(
        self,
        state_queue: Optional[asyncio.Queue] = None,
        review_future: Optional[asyncio.Future] = None,
        enable_user_review: bool = False,
    ):
        self.state_queue = state_queue
        self.review_future = review_future
        self.enable_user_review = enable_user_review
        self.search_chain = SearchChain(source=SOURCE_SEMANTIC_SCHOLAR)
        self.reading_chain = ReadingChain()
        self.analysis_chain = AnalysisChain()
        self.writing_chain = WritingChain(enable_agents=True)
        self.report_chain = ReportChain()

    async def run(self, user_request: str, max_papers: int = 20) -> WorkflowState:
        """
        执行完整工作流

        Args:
            user_request: 用户原始请求
            max_papers: 最大论文数量
        """
        state = WorkflowState(user_request=user_request, max_papers=max_papers)
        queue = self.state_queue

        try:
            # ============ Step 1: 搜索 ============
            logger.info(f"[1/5] 开始搜索: {user_request}")
            if queue:
                await queue.put(BackToFrontData(
                    step="searching", state="thinking",
                    data=f"正在分析需求: {user_request[:100]}...",
                ))
            papers = await self.search_chain.run(user_request, max_papers, queue)
            state.search_results = papers

            if not papers:
                state.error = "未找到相关论文"
                if queue:
                    await queue.put(BackToFrontData(step="failed", state="error", data=state.error))
                return state

            # ============ Step 2: 阅读 ============
            logger.info(f"[2/5] 开始阅读 {len(papers)} 篇论文")
            if queue:
                await queue.put(BackToFrontData(
                    step="reading", state="thinking",
                    data=f"正在阅读 {len(papers)} 篇论文的摘要和内容...",
                ))
            extracted = await self.reading_chain.run(papers, queue)
            state.extracted_data = extracted

            if not extracted.papers:
                state.error = "论文提取失败"
                if queue:
                    await queue.put(BackToFrontData(step="failed", state="error", data=state.error))
                return state

            # ============ Step 3: 分析（三阶段）============
            logger.info(f"[3/5] 开始分析 {len(extracted.papers)} 篇论文")
            if queue:
                await queue.put(BackToFrontData(
                    step="analyzing", state="thinking",
                    data=f"正在对 {len(extracted.papers)} 篇论文进行三阶段分析\n(聚类 -> 深度分析 -> 全局分析)...",
                ))
            analysis = await self.analysis_chain.run(user_request, extracted, queue)
            state.analysis_result = analysis

            # ============ Step 4: 写作（多 Agent 协作）============
            logger.info("[4/5] 开始写作（检索+写作+审阅协作）")
            if queue:
                await queue.put(BackToFrontData(
                    step="writing", state="thinking",
                    data="正在根据分析结果规划写作大纲...\n（将启用检索增强和自动审阅）",
                ))
            writing = await self.writing_chain.run(user_request, extracted, analysis, queue)
            state.writing_result = writing

            # ============ Step 5: 报告组装 ============
            logger.info("[5/5] 生成报告")
            if queue:
                await queue.put(BackToFrontData(
                    step="reporting", state="thinking",
                    data="正在组装最终调研报告...",
                ))
            report = await self.report_chain.run(writing, queue)
            state.report_markdown = report

            # 完成
            if queue:
                await queue.put(BackToFrontData(step="finished", state="finished", data=None))

            logger.info("工作流完成!")
            return state

        except Exception as e:
            err_msg = f"工作流执行失败: {str(e)}"
            logger.error(err_msg, exc_info=True)
            state.error = err_msg
            if queue:
                await queue.put(BackToFrontData(step="failed", state="error", data=err_msg))
            return state