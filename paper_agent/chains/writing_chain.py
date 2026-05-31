"""写作 Chain - 基于 LangChain LCEL，支持大纲生成 + 三 Agent 并行章节写作"""

import re
import json
import logging
from typing import List, Optional

import asyncio
from langchain_openai import ChatOpenAI

from paper_agent.models import (
    ExtractedPapersData, AnalysisResult, SectionTask, WritingResult,
    BackToFrontData, StepName,
)
from paper_agent.prompts import outline_prompt, section_writing_prompt
from paper_agent.config import config
from paper_agent.agents.retrieval_agent import RetrievalAgent
from paper_agent.agents.review_agent import ReviewAgent

logger = logging.getLogger(__name__)

# 最大审阅-修改迭代次数
MAX_REVIEW_ITERATIONS = 2


class WritingChain:
    """论文写作链：分析结果 -> 大纲 -> 并行写作（writing + retrieval + review）-> 章节列表"""

    def __init__(
        self,
        model_type: str = "default-model",
        enable_agents: bool = True,  # 是否启用多 Agent 协作
    ):
        self.enable_agents = enable_agents
        llm_cfg = config.get_llm_config(model_type)
        self.llm = ChatOpenAI(
            model=llm_cfg["model"],
            api_key=llm_cfg["api_key"],
            base_url=llm_cfg["base_url"],
            temperature=0.5,
        )
        self.llm_stream = ChatOpenAI(
            model=llm_cfg["model"],
            api_key=llm_cfg["api_key"],
            base_url=llm_cfg["base_url"],
            temperature=0.5,
            streaming=True,
        )
        self.outline_chain = outline_prompt | self.llm

        # Agent 实例（懒加载）
        self.retrieval_agent: Optional[RetrievalAgent] = None
        self.review_agent: Optional[ReviewAgent] = None

    def _init_agents(self):
        """初始化 Agent 实例"""
        if self.enable_agents:
            if self.retrieval_agent is None:
                self.retrieval_agent = RetrievalAgent()
            if self.review_agent is None:
                self.review_agent = ReviewAgent()

    def _parse_outline(self, outline_text: str) -> List[SectionTask]:
        """解析 LLM 生成的大纲文本，提取章节列表"""
        sections = []
        # 匹配类似 "1.1 标题 (描述)" 或 "1 标题 (描述)" 的模式
        pattern = r'(\d+(?:\.\d+)?)\s+(.+?)(?:\s*\((.+?)\))?\s*$'
        for line in outline_text.strip().split("\n"):
            line = line.strip()
            if not line:
                continue
            match = re.match(pattern, line)
            if match:
                sections.append(SectionTask(
                    index=len(sections),
                    title=f"{match.group(1)} {match.group(2).strip()}",
                    description=match.group(3).strip() if match.group(3) else "",
                ))
            elif sections:
                # 可能是续行内容
                sections[-1].description += " " + line

        # 回退：如果没有解析到章节，按行分割
        if not sections:
            for i, line in enumerate(outline_text.strip().split("\n")):
                line = line.strip()
                if line:
                    sections.append(SectionTask(index=i, title=line, description=""))

        return sections

    async def _write_section(
        self,
        section: SectionTask,
        user_request: str,
        global_analysis: str,
        papers_json: str,
        state_queue=None,
    ) -> SectionTask:
        """写作单个章节（流式输出 + 可选 Agent 协作）"""
        try:
            if state_queue:
                await state_queue.put(BackToFrontData(
                    step=f"section_writing_{section.index + 1}",
                    state="initializing", data=None,
                ))

            # === Phase 1: 检索增强（如果启用 Agent） ===
            retrieval_result = None
            if self.enable_agents:
                self._init_agents()
                if self.retrieval_agent:
                    try:
                        if state_queue:
                            await state_queue.put(BackToFrontData(
                                step=f"section_writing_{section.index + 1}",
                                state="thinking",
                                data=f"正在检索「{section.title}」相关补充资料...",
                            ))

                        retrieval_result = await self.retrieval_agent.retrieve(
                            query=f"{user_request} {section.title} {section.description}",
                            section_title=section.title,
                            section_description=section.description,
                        )
                    except Exception as e:
                        logger.warning(f"检索失败，跳过检索增强: {e}")

            # 构建增强的写作 prompt
            retrieval_context = ""
            if retrieval_result and retrieval_result.get("summary"):
                retrieval_context = f"""

【补充检索资料】
{retrieval_result['summary']}

【引用来源】
"""
                for p in retrieval_result.get("papers", [])[:3]:
                    retrieval_context += "- {} ({})\n".format(p['title'], p.get('url', ''))
                for d in retrieval_result.get("knowledge_docs", [])[:3]:
                    retrieval_context += "- [知识库] {}\n".format(d['metadata'].get('filename', d['id']))

            chain = section_writing_prompt | self.llm_stream
            full_content = ""

            async for chunk in chain.astream({
                "user_request": user_request,
                "section_task": f"{section.title}: {section.description}\n{retrieval_context}",
                "global_analysis": global_analysis[:3000],
                "papers_json": papers_json[:5000],
            }):
                content = chunk.content
                full_content += content

                if state_queue:
                    if "<|im_start|>" in content or "<|im_end|>" in content:
                        continue
                    await state_queue.put(BackToFrontData(
                        step=f"section_writing_{section.index + 1}",
                        state="generating", data=content,
                    ))

            # === Phase 2: 审阅 + 修改（如果启用 Agent） ===
            if self.enable_agents and self.review_agent:
                for iteration in range(MAX_REVIEW_ITERATIONS):
                    try:
                        if state_queue:
                            await state_queue.put(BackToFrontData(
                                step=f"section_writing_{section.index + 1}",
                                state="thinking",
                                data=f"正在审阅「{section.title}」(第{iteration + 1}轮)...",
                            ))

                        review_result = await self.review_agent.review(
                            section_title=section.title,
                            section_content=full_content,
                            section_description=section.description,
                            user_request=user_request,
                        )

                        if review_result["passed"]:
                            if state_queue:
                                await state_queue.put(BackToFrontData(
                                    step=f"section_writing_{section.index + 1}",
                                    state="generating",
                                    data=f"\n\n✅ 「{section.title}」审阅通过 (评级: {review_result['rating']})\n",
                                ))
                            logger.info(f"章节 {section.title} 审阅通过")
                            break
                        else:
                            # 根据审阅意见修改
                            if state_queue:
                                await state_queue.put(BackToFrontData(
                                    step=f"section_writing_{section.index + 1}",
                                    state="generating",
                                    data=f"\n\n🔧 正在根据审阅意见修改...\n问题：{'; '.join(review_result['issues'][:3])}\n",
                                ))

                            revision_prompt = f"""请根据以下审阅意见修改内容：

【审阅问题】
{chr(10).join(f'- {issue}' for issue in review_result['issues'])}

【修改建议】
{chr(10).join(f'- {s}' for s in review_result['suggestions'])}

【当前内容】
{full_content}

请输出修改后的完整内容。"""

                            # 非流式修改（避免过多 SSE 消息）
                            revision_response = await self.llm.ainvoke(revision_prompt)
                            full_content = revision_response.content

                    except Exception as e:
                        logger.warning(f"审阅迭代 {iteration + 1} 失败: {e}")
                        break

            section.content = full_content

            if state_queue:
                await state_queue.put(BackToFrontData(
                    step=f"section_writing_{section.index + 1}",
                    state="completed", data=None,
                ))

        except Exception as e:
            err_type = type(e).__name__
            logger.error(f"写作章节 {section.title} 失败 [{err_type}]: {e}")

            # 连接错误：等 5 秒重试一次
            if "Connection" in err_type or "connection" in str(e):
                logger.warning(f"连接错误，等待 5s 后重试章节 {section.title}...")
                try:
                    await asyncio.sleep(5)
                    return await self._write_section(
                        section, user_request,
                        global_analysis, papers_json, state_queue,
                    )
                except Exception as e2:
                    logger.error(f"重试章节 {section.title} 再次失败: {type(e2).__name__}: {e2}")

            section.content = f"## {section.title}\n\n（章节生成失败: {err_type}: {str(e)}）"
            if state_queue:
                await state_queue.put(BackToFrontData(
                    step=f"section_writing_{section.index + 1}",
                    state="error", data=str(e),
                ))

        return section

    async def run(
        self,
        user_request: str,
        extracted_data: ExtractedPapersData,
        analysis_result: AnalysisResult,
        state_queue=None,
    ) -> WritingResult:
        """
        执行写作流程

        Args:
            user_request: 用户原始请求
            extracted_data: 论文提取数据
            analysis_result: 分析结果
            state_queue: SSE 状态队列
        """
        if state_queue:
            await state_queue.put(BackToFrontData(step="writing", state="initializing", data=None))

        try:
            # Step 1: 生成大纲
            if state_queue:
                await state_queue.put(BackToFrontData(
                    step="writing", state="thinking",
                    data="正在生成写作大纲...",
                ))

            outline_response = await self.outline_chain.ainvoke({
                "user_request": user_request,
                "global_analysis": analysis_result.global_analysis,
            })
            sections = self._parse_outline(outline_response.content)

            if not sections:
                logger.warning("大纲解析为空，使用默认大纲")
                sections = [
                    SectionTask(index=0, title="1 引言", description="介绍研究背景和意义"),
                    SectionTask(index=1, title="2 技术综述", description="总结主要技术方法"),
                    SectionTask(index=2, title="3 总结与展望", description="总结发现和未来方向"),
                ]

            logger.info(f"生成大纲: {[s.title for s in sections]}")

            # Step 2: 并行写作各章节
            papers_json = json.dumps(
                [p.model_dump() for p in extracted_data.papers],
                ensure_ascii=False,
            )

            # ★ 并发控制：限制同时写作的章节数，避免打爆 LLM/Embedding API
            _semaphore = asyncio.Semaphore(1)  # 串行写作，避免 API 并发限流

            async def _write_with_limit(section: SectionTask) -> SectionTask:
                async with _semaphore:
                    return await self._write_section(
                        section, user_request,
                        analysis_result.global_analysis, papers_json, state_queue,
                    )

            writing_results = await asyncio.gather(
                *[_write_with_limit(s) for s in sections],
                return_exceptions=True,
            )

            # 收集结果
            final_sections = []
            for i, result in enumerate(writing_results):
                if isinstance(result, Exception):
                    logger.error(f"章节 {i} 写作异常: {result}")
                    final_sections.append(SectionTask(
                        index=i, title=sections[i].title,
                        content=f"## {sections[i].title}\n\n（章节生成异常）",
                    ))
                else:
                    final_sections.append(result)

            if state_queue:
                await state_queue.put(BackToFrontData(
                    step="writing", state="completed",
                    data=f"写作完成，共 {len(final_sections)} 个章节",
                ))

            return WritingResult(sections=final_sections)

        except Exception as e:
            err_msg = f"写作失败: {str(e)}"
            logger.error(err_msg)
            if state_queue:
                await state_queue.put(BackToFrontData(
                    step="writing", state="error", data=err_msg,
                ))
            return WritingResult()
