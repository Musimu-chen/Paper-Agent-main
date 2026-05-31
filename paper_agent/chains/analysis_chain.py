"""分析 Chain - 基于 LangChain LCEL，三阶段分析（聚类 → 深度分析 → 全局分析）"""

import json
import logging
from typing import List, Dict, Any

import asyncio
import numpy as np
from langchain_openai import ChatOpenAI
from sklearn.cluster import KMeans

from paper_agent.models import (
    ExtractedPapersData, ExtractedPaperData, AnalysisResult,
    ClusterInfo, BackToFrontData, StepName,
)
from paper_agent.prompts import cluster_prompt, analysis_prompt
from paper_agent.config import config

logger = logging.getLogger(__name__)

# 深度分析提示词（每个聚类独立分析）
DEEP_ANALYSIS_PROMPT = """你是一位专业的学术研究分析师。请针对以下特定主题的论文聚类进行深入分析。

分析维度：
1. 技术路线 - 该主题下的核心技术发展脉络和重要方法
2. 方法对比 - 不同论文之间方法的优劣对比（效率、成本、适用场景）
3. 应用场景 - 该主题技术的主要应用场景和需求差异
4. 研究趋势 - 当前关注的技术方向和新趋势
5. 关键发现 - 该聚类中最重要的1-2个发现或突破

请以结构化的 Markdown 格式输出分析结果。"""


class AnalysisChain:
    """论文分析链：提取数据 -> 聚类 -> 深度分析 -> 全局分析"""

    def __init__(self, model_type: str = "default-model"):
        llm_cfg = config.get_llm_config(model_type)
        self.llm = ChatOpenAI(
            model=llm_cfg["model"],
            api_key=llm_cfg["api_key"],
            base_url=llm_cfg["base_url"],
            temperature=0.3,
        )
        self.cluster_chain = cluster_prompt | self.llm
        self.analysis_chain = analysis_prompt | self.llm
        self.deep_analysis_chain = ChatOpenAI(
            model=llm_cfg["model"],
            api_key=llm_cfg["api_key"],
            base_url=llm_cfg["base_url"],
            temperature=0.3,
        )

    def _get_embeddings(self, texts: List[str]) -> np.ndarray:
        """使用配置的嵌入模型获取文本向量"""
        from openai import OpenAI
        from paper_agent.config import config

        api_key = config.get("SILICONFLOW_API_KEY", "")
        base_url = config.get("LLM_BASE_URL", "https://api.siliconflow.cn/v1")
        model_name = config.get("EMBEDDING_MODEL", "Qwen/Qwen3-Embedding-8B")

        if not api_key:
            raise ValueError("SILICONFLOW_API_KEY 未配置，无法获取嵌入向量")

        client = OpenAI(
            api_key=api_key,
            base_url=base_url,
        )

        response = client.embeddings.create(
            model=model_name,
            input=texts,
        )
        return np.array([item.embedding for item in response.data])

    def _prepare_text_for_embedding(self, paper: ExtractedPaperData) -> str:
        """准备嵌入文本"""
        parts = []
        if paper.core_problem:
            parts.append(f"Problem: {paper.core_problem}")
        if paper.key_methodology and paper.key_methodology.name:
            parts.append(f"Method: {paper.key_methodology.name} - {paper.key_methodology.principle}")
        if paper.main_results:
            parts.append(f"Results: {paper.main_results}")
        if paper.contributions:
            parts.append(f"Contributions: {'; '.join(paper.contributions)}")
        return " ".join(parts)

    def _cluster_papers(self, papers: List[ExtractedPaperData]) -> List[List[int]]:
        """使用 KMeans 对论文进行聚类，返回每个聚类中的论文索引"""
        if len(papers) <= 2:
            return [list(range(len(papers)))]

        texts = [self._prepare_text_for_embedding(p) for p in papers]
        try:
            embeddings = self._get_embeddings(texts)
        except Exception as e:
            logger.warning(f"获取嵌入向量失败，跳过聚类: {e}")
            return [list(range(len(papers)))]

        max_k = min(5, len(papers) - 1)
        if max_k < 2:
            return [list(range(len(papers)))]

        # 肘部法则确定聚类数
        inertias = []
        for k in range(1, max_k + 1):
            km = KMeans(n_clusters=k, random_state=42, n_init=10)
            km.fit(embeddings)
            inertias.append(km.inertia_)

        if len(inertias) >= 3:
            diffs = [inertias[i - 1] - inertias[i] for i in range(1, len(inertias))]
            n_clusters = diffs.index(max(diffs)) + 2
        else:
            n_clusters = min(2, max_k)

        n_clusters = min(n_clusters, max_k)
        km = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
        labels = km.fit_predict(embeddings)

        clusters = [[] for _ in range(n_clusters)]
        for idx, label in enumerate(labels):
            clusters[label].append(idx)
        return clusters

    async def _deep_analyze_cluster(
        self,
        cluster: ClusterInfo,
    ) -> str:
        """
        第二阶段: 对单个聚类进行深度分析

        Args:
            cluster: 聚类信息（含主题、论文列表）

        Returns:
            该聚类的深度分析文本
        """
        prompt = f"""{DEEP_ANALYSIS_PROMPT}

## 聚类信息
- 聚类主题：{cluster.theme}
- 核心关键词：{', '.join(cluster.keywords) if cluster.keywords else '无'}
- 论文数量：{cluster.paper_count}

## 详细论文数据
{json.dumps(cluster.papers[:5], ensure_ascii=False, indent=2)}

请开始深度分析："""

        try:
            response = await self.deep_analysis_chain.ainvoke(prompt)
            return response.content
        except Exception as e:
            logger.warning(f"聚类 {cluster.cluster_id} 深度分析失败: {e}")
            return f"深度分析暂不可用: {str(e)}"

    async def run(
        self,
        user_request: str,
        extracted_data: ExtractedPapersData,
        state_queue=None,
    ) -> AnalysisResult:
        """
        执行三阶段分析流程

        阶段1: KMeans 聚类 + LLM 主题生成
        阶段2: 每个聚类独立深度分析（并行）
        阶段3: 全局综合分析

        Args:
            user_request: 用户原始请求
            extracted_data: 论文提取数据
            state_queue: SSE 状态队列
        """
        if state_queue:
            await state_queue.put(BackToFrontData(step="analyzing", state="initializing", data=None))

        papers = extracted_data.papers
        if not papers:
            return AnalysisResult()

        try:
            # ========== 阶段1: 聚类分析 ==========
            if state_queue:
                await state_queue.put(BackToFrontData(
                    step="analyzing", state="thinking",
                    data="正在进行论文聚类分析（KMeans + LLM 主题标注）...",
                ))

            cluster_indices = self._cluster_papers(papers)

            # 为每个聚类生成主题
            clusters_info = []
            for cid, indices in enumerate(cluster_indices):
                cluster_papers = [papers[i].model_dump() for i in indices]

                # LLM 生成主题描述
                try:
                    cluster_response = await self.cluster_chain.ainvoke(
                        {"papers_json": json.dumps(cluster_papers[:3], ensure_ascii=False, indent=2)}
                    )
                    theme_text = cluster_response.content

                    theme = "未分类研究主题"
                    keywords = ["research"]
                    for line in theme_text.split("\n"):
                        if "主题描述" in line or "主题" in line:
                            parts = line.split("：") if "：" in line else line.split(":")
                            if len(parts) > 1:
                                theme = parts[-1].strip().strip("[]")
                        elif "关键词" in line:
                            parts = line.split("：") if "：" in line else line.split(":")
                            if len(parts) > 1:
                                kw_str = parts[-1].strip().strip("[]")
                                keywords = [k.strip() for k in kw_str.replace("，", ",").split(",") if k.strip()][:5]

                except Exception as e:
                    logger.warning(f"聚类 {cid} 主题生成失败: {e}")
                    theme = f"聚类 {cid + 1}"
                    keywords = []

                clusters_info.append(ClusterInfo(
                    cluster_id=cid,
                    theme=theme,
                    keywords=keywords,
                    paper_count=len(indices),
                    papers=cluster_papers,
                ))

            if state_queue:
                await state_queue.put(BackToFrontData(
                    step="analyzing", state="thinking",
                    data=f"聚类完成，共 {len(clusters_info)} 个主题，正在进行深度分析...",
                ))

            # ========== 阶段2: 深度分析（并行处理所有聚类） ==========
            deep_analysis_tasks = [
                self._deep_analyze_cluster(cluster)
                for cluster in clusters_info
            ]
            deep_analysis_results = await asyncio.gather(
                *deep_analysis_tasks, return_exceptions=True,
            )

            # 合并深度分析结果
            for i, result in enumerate(deep_analysis_results):
                if isinstance(result, Exception):
                    logger.error(f"聚类 {i} 深度分析异常: {result}")
                    deep_analysis_results[i] = f"深度分析失败: {str(result)}"

            if state_queue:
                await state_queue.put(BackToFrontData(
                    step="analyzing", state="thinking",
                    data=f"深度分析完成，共 {len(clusters_info)} 个主题，正在进行全局综合分析...",
                ))

            # ========== 阶段3: 全局分析 ==========
            # 将深度分析结果作为额外上下文传递给全局分析
            deep_context = "\n\n---\n\n".join([
                f"## 聚类{i+1}深度分析: {clusters_info[i].theme}\n{result}"
                for i, result in enumerate(deep_analysis_results)
            ])

            papers_json = json.dumps(
                [p.model_dump() for p in papers],
                ensure_ascii=False, indent=2,
            )

            # 增强的分析 prompt
            enhanced_analysis_input = (
                f"用户需求：{user_request}\n\n"
                f"## 各聚类深度分析结果\n{deep_context[:4000]}\n\n"
                f"## 全部论文数据\n{papers_json[:3000]}\n\n"
                f"请基于以上信息，生成包含【技术发展趋势、方法论对比、性能表现评估、局限性与挑战、建议与展望】五大模块的全局分析报告。"
            )

            analysis_response = await self.analysis_chain.ainvoke(enhanced_analysis_input)
            global_analysis = analysis_response.content

            if state_queue:
                await state_queue.put(BackToFrontData(
                    step="analyzing", state="completed",
                    data=global_analysis[:500] + "..." if len(global_analysis) > 500 else global_analysis,
                ))

            return AnalysisResult(
                clusters=clusters_info,
                global_analysis=global_analysis,
            )

        except Exception as e:
            err_msg = f"分析失败: {str(e)}"
            logger.error(err_msg)
            if state_queue:
                await state_queue.put(BackToFrontData(
                    step="analyzing", state="error", data=err_msg,
                ))
            return AnalysisResult()