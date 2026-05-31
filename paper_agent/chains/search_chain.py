"""检索 Chain - 基于 LangChain LCEL，支持 Semantic Scholar + arXiv 双源"""

import json
import logging
from typing import List, Optional

from langchain_core.output_parsers import PydanticOutputParser
from langchain_openai import ChatOpenAI

from paper_agent.models import SearchQuery, PaperMetadata, BackToFrontData, StepName
from paper_agent.prompts import search_prompt
from paper_agent.config import config
from paper_agent.services.arxiv_client import ArxivClient
from paper_agent.services.semantic_scholar_client import SemanticScholarClient

logger = logging.getLogger(__name__)

# 论文来源
SOURCE_SEMANTIC_SCHOLAR = "semantic_scholar"
SOURCE_ARXIV = "arxiv"


class SearchChain:
    """论文检索链：用户需求 -> 检索条件 -> 论文列表（优先 Semantic Scholar，回退 arXiv）"""

    def __init__(
        self,
        model_type: str = "default-model",
        source: str = SOURCE_SEMANTIC_SCHOLAR,
    ):
        self.source = source
        llm_cfg = config.get_llm_config(model_type)
        self.llm = ChatOpenAI(
            model=llm_cfg["model"],
            api_key=llm_cfg["api_key"],
            base_url=llm_cfg["base_url"],
            temperature=0.1,
        )
        self.parser = PydanticOutputParser(pydantic_object=SearchQuery)

        # 双源客户端
        self.semantic_scholar_client: Optional[SemanticScholarClient] = None
        self.arxiv_client: Optional[ArxivClient] = None

        if source == SOURCE_SEMANTIC_SCHOLAR:
            semantic_api_key = config.get("SEMANTIC_SCHOLAR_API_KEY", None)
            self.semantic_scholar_client = SemanticScholarClient(api_key=semantic_api_key)
            self.arxiv_client = ArxivClient()  # 作为回退
        elif source == SOURCE_ARXIV:
            self.arxiv_client = ArxivClient()

        # 构建 LCEL Chain
        self.chain = search_prompt | self.llm | self.parser

    async def _cleanup_clients(self):
        """清理 HTTP 客户端"""
        if self.semantic_scholar_client:
            await self.semantic_scholar_client.close()

    async def _search_semantic_scholar(
        self,
        search_query: SearchQuery,
        max_papers: int,
        state_queue=None,
    ) -> List[PaperMetadata]:
        """通过 Semantic Scholar 检索"""
        if not self.semantic_scholar_client:
            raise RuntimeError("Semantic Scholar 客户端未初始化")

        if state_queue:
            await state_queue.put(BackToFrontData(
                step="searching", state="generating",
                data=f"正在从 Semantic Scholar 检索论文...",
            ))

        papers = await self.semantic_scholar_client.search(
            queries=search_query.queries,
            max_results=max_papers,
            start_date=search_query.start_date,
            end_date=search_query.end_date,
        )
        return papers

    async def _search_arxiv(
        self,
        search_query: SearchQuery,
        max_papers: int,
        state_queue=None,
    ) -> List[PaperMetadata]:
        """通过 arXiv 检索（作为回退方案）"""
        if not self.arxiv_client:
            raise RuntimeError("arXiv 客户端未初始化")

        if state_queue:
            await state_queue.put(BackToFrontData(
                step="searching", state="generating",
                data="Semantic Scholar 不可用，正在从 arXiv 检索论文...",
            ))

        papers = await self.arxiv_client.search(
            queries=search_query.queries,
            max_results=max_papers,
            start_date=search_query.start_date,
            end_date=search_query.end_date,
        )

        # arXiv 返回的是原始格式，需要确保是 PaperMetadata 列表
        result = []
        for p in papers:
            if isinstance(p, PaperMetadata):
                result.append(p)
            elif isinstance(p, dict):
                result.append(PaperMetadata(
                    paper_id=p.get("arxiv_id", p.get("paper_id", "")),
                    title=p.get("title", ""),
                    authors=p.get("authors", []),
                    summary=p.get("abstract", p.get("summary", "")),
                    published_date=p.get("published", ""),
                    url=p.get("link", p.get("url", "")),
                    categories=p.get("categories", []),
                    primary_category=p.get("primary_category", "") or (
                        p.get("categories", [""])[0] if p.get("categories") else ""
                    ),
                ))
        return result

    async def run(
        self,
        user_request: str,
        max_papers: int = 20,
        state_queue=None,
    ) -> List[PaperMetadata]:
        """
        执行检索流程（优先 Semantic Scholar，失败时回退 arXiv）

        Args:
            user_request: 用户原始请求
            max_papers: 最大论文数量
            state_queue: SSE 状态队列
        """
        if state_queue:
            await state_queue.put(BackToFrontData(
                step="searching", state="initializing", data=None,
            ))

        try:
            # Step 1: LLM 生成检索条件
            if state_queue:
                await state_queue.put(BackToFrontData(
                    step="searching", state="thinking",
                    data="正在分析需求，生成检索条件...",
                ))

            search_query: SearchQuery = await self.chain.ainvoke({"user_request": user_request})
            logger.info(f"生成检索条件: {search_query.model_dump_json()}")

            if state_queue:
                await state_queue.put(BackToFrontData(
                    step="searching", state="generating",
                    data=f"检索条件: {json.dumps(search_query.model_dump(), ensure_ascii=False)}",
                ))

            # Step 2: 调用论文 API 检索（Semantic Scholar 优先）
            papers = []
            search_error = None

            if self.source == SOURCE_SEMANTIC_SCHOLAR:
                try:
                    papers = await self._search_semantic_scholar(
                        search_query, max_papers, state_queue,
                    )
                except Exception as e:
                    logger.warning(f"Semantic Scholar 检索失败，尝试回退 ArXiv: {e}")
                    search_error = e
                    # 回退到 ArXiv
                    if self.arxiv_client:
                        try:
                            papers = await self._search_arxiv(
                                search_query, max_papers, state_queue,
                            )
                        except Exception as e2:
                            logger.error(f"ArXiv 回退也失败: {e2}")
                            search_error = e2
            elif self.source == SOURCE_ARXIV:
                papers = await self._search_arxiv(
                    search_query, max_papers, state_queue,
                )

            if not papers:
                err_msg = "没有找到相关论文"
                if search_error:
                    err_msg += f" ({str(search_error)[:100]})"
                if state_queue:
                    await state_queue.put(BackToFrontData(
                        step="searching", state="error",
                        data=err_msg + "，请尝试其他查询条件",
                    ))
                return []

            if state_queue:
                source_name = "Semantic Scholar" if self.source == SOURCE_SEMANTIC_SCHOLAR else "arXiv"
                await state_queue.put(BackToFrontData(
                    step="searching", state="completed",
                    data=f"从 {source_name} 搜索完成，共找到 {len(papers)} 篇论文",
                ))

            return papers

        except Exception as e:
            err_msg = f"搜索失败: {str(e)}"
            logger.error(err_msg)
            if state_queue:
                await state_queue.put(BackToFrontData(
                    step="searching", state="error", data=err_msg,
                ))
            return []
