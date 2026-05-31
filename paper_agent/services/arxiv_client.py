"""arXiv 论文检索服务 - MOCK 模式（用于跑通流程，真实代码已注释保留）"""

import logging
from typing import List, Optional

from paper_agent.models import PaperMetadata

logger = logging.getLogger(__name__)


class ArxivClient:
    """arXiv 论文检索客户端 - 当前为 MOCK 模式"""

    def __init__(self, delay_seconds: float = 15.0):
        self.delay_seconds = delay_seconds

    async def close(self):
        pass

    async def search(
        self,
        queries: List[str],
        max_results: int = 20,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> List[PaperMetadata]:
        """
        MOCK 搜索 - 返回假数据用于跑通流程
        真实实现已注释在文件底部，取消注释即可恢复
        """
        logger.warning("⚠️ [ArXiv 回退] 使用 MOCK 数据（Semantic Scholar 不可用）")
        logger.info(f"[MOCK] arXiv 查询: {queries}")

        mock_papers = [
            PaperMetadata(
                paper_id="2401.12345",
                title="Large Language Models for Code Generation: A Survey",
                authors=["Zhang San", "Li Si", "Wang Wu"],
                summary="This paper provides a comprehensive survey on large language models (LLMs) for code generation. We review recent advances, methodologies, and applications of LLMs in software engineering, including code completion, bug fixing, and program synthesis. Our analysis shows that LLMs have achieved remarkable performance but still face challenges in reasoning and correctness.",
                published=2024,
                published_date="2024-01-15T00:00:00",
                url="http://arxiv.org/abs/2401.12345",
                pdf_url="http://arxiv.org/pdf/2401.12345",
                primary_category="cs.AI",
                categories=["cs.AI", "cs.SE", "cs.CL"],
            ),
            PaperMetadata(
                paper_id="2402.23456",
                title="Scaling Laws for Neural Network Compression",
                authors=["Alice Johnson", "Bob Smith"],
                summary="We investigate the scaling behavior of large neural network compression techniques. Our experiments demonstrate that model size, compression ratio, and task performance follow predictable scaling laws. These findings provide guidance for efficiently deploying large models in resource-constrained environments.",
                published=2024,
                published_date="2024-02-20T00:00:00",
                url="http://arxiv.org/abs/2402.23456",
                pdf_url="http://arxiv.org/pdf/2402.23456",
                primary_category="cs.LG",
                categories=["cs.LG", "cs.AI"],
            ),
            PaperMetadata(
                paper_id="2305.67890",
                title="Attention Mechanisms in Large-Scale Transformers",
                authors=["Chen Liu", "David Brown", "Emma Wilson"],
                summary="This work analyzes attention mechanisms in large-scale Transformer models. We propose a novel sparse attention pattern that reduces computational complexity from O(n^2) to O(n log n) while maintaining model quality. Experiments on language modeling and translation tasks show competitive results with significantly lower resource requirements.",
                published=2023,
                published_date="2023-05-10T00:00:00",
                url="http://arxiv.org/abs/2305.67890",
                pdf_url="http://arxiv.org/pdf/2305.67890",
                primary_category="cs.CL",
                categories=["cs.CL", "cs.AI", "cs.LG"],
            ),
            PaperMetadata(
                paper_id="2310.11111",
                title="Efficient Fine-Tuning of Large Pre-trained Models",
                authors=["Michael Zhang", "Sarah Lee"],
                summary="We present a comprehensive study on parameter-efficient fine-tuning (PEFT) methods for large pre-trained models. Our method, AdaLoRA, adaptively allocates parameter budgets among weight matrices based on importance scores. Results across NLP and vision tasks show that AdaLoRA achieves better performance with fewer trainable parameters compared to existing PEFT methods.",
                published=2023,
                published_date="2023-10-05T00:00:00",
                url="http://arxiv.org/abs/2310.11111",
                pdf_url="http://arxiv.org/pdf/2310.11111",
                primary_category="cs.LG",
                categories=["cs.LG", "cs.CL"],
            ),
            PaperMetadata(
                paper_id="2403.44444",
                title="Benchmarking Reasoning Capabilities of Large Language Models",
                authors=["Yao Wang", "James Taylor", "Lisa Chen"],
                summary="This paper introduces a new benchmark for evaluating the reasoning capabilities of large language models. We test 20 state-of-the-art models on mathematical reasoning, commonsense reasoning, and logical inference tasks. Our findings reveal that while LLMs excel at pattern recognition, they still struggle with multi-step logical reasoning and causal inference.",
                published=2024,
                published_date="2024-03-18T00:00:00",
                url="http://arxiv.org/abs/2403.44444",
                pdf_url="http://arxiv.org/pdf/2403.44444",
                primary_category="cs.AI",
                categories=["cs.AI", "cs.CL"],
            ),
        ]

        result = mock_papers[:max_results]
        logger.info(f"[MOCK] 返回 {len(result)} 篇论文（假数据）")
        return result

    def _format_date(self, date: str) -> str:
        """格式化日期为 arXiv API 格式 YYYYMMDDTTTT"""
        from datetime import datetime

        for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d", "%Y"):
            try:
                parsed = datetime.strptime(date, fmt)
                return parsed.strftime("%Y%m%d0000")
            except ValueError:
                continue
        return "999912312359"


# ==============================================================================
# 以下是真实 arXiv 调用代码，已注释保留
# 恢复时：1. 取消下方注释  2. 注释掉上方 MOCK 的 search() 方法  3. 把 import 加回文件头部
# ==============================================================================
# import asyncio
# import arxiv
#
# class ArxivClient:
#     """arXiv 论文检索客户端 - 基于 arxiv Python 库"""
#
#     def __init__(self, delay_seconds: float = 15.0):
#         """
#         Args:
#             delay_seconds: 两次请求之间的最小间隔（秒），arXiv 建议至少 3 秒，批量请求建议 10-15 秒
#         """
#         self.delay_seconds = delay_seconds
#         self._client = arxiv.Client(delay_seconds=delay_seconds, num_retries=3)
#
#     async def close(self):
#         """关闭客户端"""
#         pass
#
#     async def search(
#         self,
#         queries: List[str],
#         max_results: int = 20,
#         start_date: Optional[str] = None,
#         end_date: Optional[str] = None,
#     ) -> List[PaperMetadata]:
#         """
#         搜索 arXiv 论文
#
#         Args:
#             queries: 英文检索关键词列表
#             max_results: 最大返回数量
#             start_date: 开始日期 (YYYY-MM-DD)
#             end_date: 结束日期 (YYYY-MM-DD)
#         """
#         try:
#             # 构建查询字符串
#             search_query = " OR ".join(f'all:"{q}"' for q in queries)
#
#             # 添加日期过滤（过滤 LLM 返回的 "null"/"none"/空字符串）
#             def _is_valid_date(d: Optional[str]) -> bool:
#                 return bool(d and str(d).strip().lower() not in ("null", "none", ""))
#
#             if _is_valid_date(start_date) or _is_valid_date(end_date):
#                 start_str = self._format_date(start_date) if _is_valid_date(start_date) else "190001010000"
#                 end_str = self._format_date(end_date) if _is_valid_date(end_date) else "999912312359"
#                 search_query = f"{search_query} AND submittedDate:[{start_str} TO {end_str}]"
#
#             logger.info(f"arXiv 查询: {search_query}")
#
#             # 使用 arxiv 库搜索（同步操作，放入线程池避免阻塞事件循环）
#             search = arxiv.Search(
#                 query=search_query,
#                 max_results=max_results,
#                 sort_by=arxiv.SortCriterion.Relevance,
#                 sort_order=arxiv.SortOrder.Descending,
#             )
#
#             papers = await asyncio.to_thread(self._sync_search, search)
#
#             logger.info(f"arXiv 检索完成，找到 {len(papers)} 篇论文")
#             return papers
#
#         except Exception as e:
#             logger.error(f"arXiv 检索失败: {e}")
#             return []
#
#     def _sync_search(self, search: arxiv.Search) -> List[PaperMetadata]:
#         """同步执行搜索（在线程池中调用）"""
#         papers = []
#         for result in self._client.results(search):
#             try:
#                 paper = self._convert_result(result)
#                 papers.append(paper)
#             except Exception as e:
#                 logger.warning(f"解析单篇论文失败: {e}")
#                 continue
#         return papers
#
#     def _convert_result(self, result: arxiv.Result) -> PaperMetadata:
#         """将 arxiv.Result 转换为 PaperMetadata"""
#         paper_id = result.entry_id.split("/abs/")[-1] if "/abs/" in result.entry_id else result.entry_id
#
#         # PDF 链接
#         pdf_url = ""
#         if result.pdf_url:
#             pdf_url = result.pdf_url
#
#         # 分类
#         primary_category = result.primary_category or ""
#         categories = [cat for cat in result.categories] if result.categories else []
#
#         # 发布日期
#         published_year = result.published.year if result.published else None
#         published_date = result.published.isoformat() if result.published else None
#
#         return PaperMetadata(
#             paper_id=paper_id,
#             title=result.title,
#             authors=[a.name for a in result.authors],
#             summary=result.summary,
#             published=published_year,
#             published_date=published_date,
#             url=result.entry_id,
#             pdf_url=pdf_url,
#             primary_category=primary_category,
#             categories=categories,
#         )
