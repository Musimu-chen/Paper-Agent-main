"""检索智能体 - 从知识库和向量数据库中检索补充资料"""

import json
import logging
from typing import List, Dict, Any, Optional

from langchain_openai import ChatOpenAI

from paper_agent.config import config
from paper_agent.services.vector_store import VectorStore
from paper_agent.knowledge.kb_manager import KnowledgeManager

logger = logging.getLogger(__name__)

RETRIEVAL_SYSTEM_PROMPT = """你是一名专业的资料检索员。你的职责是：
1. 根据写作需求，从可用的资料库中检索相关论文和文档
2. 整理检索结果，提取最相关的内容
3. 将整理好的资料提供给写作智能体使用

处理规则：
- 优先使用与当前写作任务最相关的内容
- 如果有引用数据，确保引用格式准确
- 如果资料不足，明确指出"未找到相关资料"
- 只返回事实性信息，不要添加个人见解"""


class RetrievalAgent:
    """检索智能体 - 双源检索（知识库 + 论文向量库）"""

    def __init__(self, model_type: str = "default-model"):
        llm_cfg = config.get_llm_config(model_type)
        self.llm = ChatOpenAI(
            model=llm_cfg["model"],
            api_key=llm_cfg["api_key"],
            base_url=llm_cfg["base_url"],
            temperature=0.1,
        )
        self.paper_vector_store = VectorStore(collection_name="paper_agent_tmp")
        self.kb_manager: Optional[KnowledgeManager] = None

    def _get_kb_manager(self) -> KnowledgeManager:
        """懒加载知识库管理器"""
        if self.kb_manager is None:
            self.kb_manager = KnowledgeManager()
        return self.kb_manager

    async def retrieve(
        self,
        query: str,
        section_title: str,
        section_description: str = "",
        n_results: int = 5,
    ) -> Dict[str, Any]:
        """
        执行双源检索

        Args:
            query: 检索查询文本
            section_title: 当前写作章节标题
            section_description: 章节描述
            n_results: 每个来源检索数量

        Returns:
            {"papers": [...], "knowledge_docs": [...], "summary": "..."}
        """
        result = {
            "papers": [],
            "knowledge_docs": [],
            "summary": "",
            "query": query,
        }

        # 源1: 搜索论文向量库（论文阅读阶段存入的）
        try:
            papers = self.paper_vector_store.query(query, n_results=n_results)
            if papers.get("metadatas") and papers["metadatas"][0]:
                metadatas = papers["metadatas"][0]
                distances = papers.get("distances", [[]])[0]
                for j, meta in enumerate(metadatas):
                    result["papers"].append({
                        "paper_id": meta.get("paper_id", ""),
                        "title": meta.get("title", ""),
                        "summary": meta.get("summary", ""),
                        "authors": (meta.get("authors", "") or "").split(", "),
                        "url": meta.get("url", ""),
                        "relevance_score": distances[j] if j < len(distances) else None,
                    })
        except Exception as e:
            logger.warning(f"论文向量检索失败: {e}")

        # 源2: 搜索用户知识库
        try:
            # 懒加载避免循环导入
            from paper_agent.api.knowledge_api import get_selected_db_id
            selected_db_id = get_selected_db_id()
            if selected_db_id:
                kb = self._get_kb_manager()
                docs = kb.query_database(selected_db_id, query, n_results=n_results)
                result["knowledge_docs"] = [
                    {
                        "id": d.get("id", ""),
                        "content": d.get("content", ""),
                        "metadata": d.get("metadata", {}),
                        "distance": d.get("distance"),
                    }
                    for d in docs
                ]
            else:
                logger.info("未选择知识库，跳过知识库检索")
        except Exception as e:
            logger.warning(f"知识库检索失败: {e}")

        # 生成检索摘要
        try:
            retrieved_texts = []
            for p in result["papers"][:3]:
                retrieved_texts.append(f"[论文] {p['title']}: {p['summary'][:200]}")
            for d in result["knowledge_docs"][:3]:
                retrieved_texts.append(f"[文档] {d['content'][:200]}")

            if retrieved_texts:
                summary_prompt = f"""请根据以下检索结果，提炼与写作章节「{section_title}」最相关的3-5条关键信息：

{chr(10).join(retrieved_texts)}"""

                summary_response = await self.llm.ainvoke(summary_prompt)
                result["summary"] = summary_response.content
        except Exception as e:
            logger.warning(f"生成检索摘要失败: {e}")
            result["summary"] = "未能生成检索摘要"

        total_found = len(result["papers"]) + len(result["knowledge_docs"])
        logger.info(
            f"检索完成: 论文 {len(result['papers'])} 篇, "
            f"知识库文档 {len(result['knowledge_docs'])} 篇, "
            f"共 {total_found} 条结果"
        )

        return result