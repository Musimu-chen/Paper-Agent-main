"""阅读 Chain - 基于 LangChain LCEL，支持并行处理"""

import json
import re
import logging
from typing import List, Tuple

from langchain_core.output_parsers import PydanticOutputParser
from langchain_openai import ChatOpenAI

from paper_agent.models import (
    PaperMetadata, ExtractedPaperData, ExtractedPapersData,
    KeyMethodology, BackToFrontData, StepName,
)
from paper_agent.prompts import reading_prompt
from paper_agent.config import config
from paper_agent.services.vector_store import VectorStore

logger = logging.getLogger(__name__)


class ReadingChain:
    """论文阅读链：论文元数据 -> 结构化提取数据"""

    def __init__(self, model_type: str = "default-model"):
        llm_cfg = config.get_llm_config(model_type)
        self.llm = ChatOpenAI(
            model=llm_cfg["model"],
            api_key=llm_cfg["api_key"],
            base_url=llm_cfg["base_url"],
            temperature=0.1,
        )
        self.parser = PydanticOutputParser(pydantic_object=ExtractedPapersData)
        self.vector_store = VectorStore(collection_name="paper_agent_tmp")

        # 构建 LCEL Chain
        self.chain = reading_prompt | self.llm | self.parser

    def _safe_model_dump(self, paper: PaperMetadata) -> str:
        """安全序列化 PaperMetadata，处理 PydanticUndefined 等不可序列化值"""
        data = paper.model_dump()
        # 清理不可序列化的值
        from pydantic_core import PydanticUndefined
        def _clean(obj):
            if isinstance(obj, dict):
                return {k: _clean(v) for k, v in obj.items() if v is not PydanticUndefined}
            if isinstance(obj, list):
                return [_clean(v) for v in obj if v is not PydanticUndefined]
            if obj is PydanticUndefined:
                return ""
            return obj
        return json.dumps(_clean(data), ensure_ascii=False, indent=2)

    async def _read_single_paper(self, paper: PaperMetadata) -> ExtractedPaperData:
        """读取单篇论文，返回结构化数据"""
        try:
            paper_info = self._safe_model_dump(paper)
            result: ExtractedPapersData = await self.chain.ainvoke({"paper_info": paper_info})
            if result.papers:
                return result.papers[0]
            return ExtractedPaperData()
        except Exception as e:
            logger.warning(f"解析论文 {paper.paper_id} 失败，尝试原始解析: {e}")
            return await self._fallback_read(paper)

    async def _fallback_read(self, paper: PaperMetadata) -> ExtractedPaperData:
        """回退方案：直接让 LLM 输出，手动解析 JSON"""
        try:
            paper_info = self._safe_model_dump(paper)
            raw = await (reading_prompt | self.llm).ainvoke({"paper_info": paper_info})

            content = raw.content.strip()
            # 清理 markdown 代码块
            if content.startswith("```"):
                content = re.sub(r"^```(?:json)?\s*", "", content)
                content = re.sub(r"\s*```$", "", content)

            data = json.loads(content)

            # 处理可能的嵌套结构
            if isinstance(data, list) and data:
                data = data[0]
            if isinstance(data, dict) and "papers" in data:
                papers_list = data["papers"]
                data = papers_list[0] if papers_list else {}

            return ExtractedPaperData.model_validate(data)
        except Exception as e2:
            logger.error(f"回退解析论文 {paper.paper_id} 也失败: {e2}")
            return ExtractedPaperData(
                core_problem=f"解析失败: {paper.title}",
                main_results=paper.summary[:200],
            )

    async def run(
        self,
        papers: List[PaperMetadata],
        state_queue=None,
    ) -> ExtractedPapersData:
        """
        并行读取多篇论文

        Args:
            papers: 论文元数据列表
            state_queue: SSE 状态队列
        """
        import asyncio

        if state_queue:
            await state_queue.put(BackToFrontData(step="reading", state="initializing", data=None))

        if not papers:
            return ExtractedPapersData()

        # 并行处理所有论文
        if state_queue:
            await state_queue.put(BackToFrontData(
                step="reading", state="generating",
                data=f"正在并行阅读 {len(papers)} 篇论文...",
            ))

        results = await asyncio.gather(
            *[self._read_single_paper(paper) for paper in papers],
            return_exceptions=True,
        )

        # 收集成功的结果
        extracted = ExtractedPapersData()
        successful_papers = []

        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"阅读论文 {papers[i].paper_id} 异常: {result}")
                continue
            if isinstance(result, ExtractedPaperData) and result.core_problem:
                extracted.papers.append(result)
                successful_papers.append(papers[i])

        # 存入向量数据库
        try:
            self.vector_store.add_papers(successful_papers, extracted)
        except Exception as e:
            logger.warning(f"向量存储失败（不影响流程）: {e}")

        if state_queue:
            await state_queue.put(BackToFrontData(
                step="reading", state="completed",
                data=f"论文阅读完成，成功提取 {len(extracted.papers)} 篇论文",
            ))

        return extracted
