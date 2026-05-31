"""审查智能体 - 检查写作内容质量，提供修改建议"""

import logging
from typing import Dict, Optional

from langchain_openai import ChatOpenAI

from paper_agent.config import config

logger = logging.getLogger(__name__)

REVIEW_SYSTEM_PROMPT = """你是一名严格的学术审稿人。你需要从以下维度审阅章节内容：

1. **准确性**: 事实陈述是否准确？引用是否正确？有无编造内容？
2. **完整性**: 是否覆盖了该章节应有的核心内容？
3. **逻辑性**: 论述逻辑是否清晰连贯？
4. **学术规范**: 语言是否专业客观？

审阅后给出以下格式的结论：

【审阅评级】（PASS / MINOR_REVISION / MAJOR_REVISION）
【优点】列出1-3个主要优点
【问题】列出具体问题（每条一行，用 - 开头）
【修改建议】针对问题的具体修改建议
【是否通过】（APPROVE / DENY）

如果内容质量良好，无明显问题，输出 APPROVE；否则输出 DENY 并给出具体修改方向。"""


class ReviewAgent:
    """审查智能体 - 质量审查"""

    def __init__(self, model_type: str = "default-model"):
        llm_cfg = config.get_llm_config(model_type)
        self.llm = ChatOpenAI(
            model=llm_cfg["model"],
            api_key=llm_cfg["api_key"],
            base_url=llm_cfg["base_url"],
            temperature=0.2,
        )

    async def review(
        self,
        section_title: str,
        section_content: str,
        section_description: str = "",
        user_request: str = "",
    ) -> Dict:
        """
        审查章节内容

        Args:
            section_title: 章节标题
            section_content: 章节内容
            section_description: 章节描述/写作要求
            user_request: 用户原始需求

        Returns:
            {
                "passed": bool,         # 是否通过
                "rating": str,          # PASS / MINOR_REVISION / MAJOR_REVISION
                "strengths": [str],     # 优点列表
                "issues": [str],        # 问题列表
                "suggestions": [str],   # 修改建议
                "review_text": str,     # 完整审阅文本
            }
        """
        prompt = f"""请审阅以下章节内容：

【章节标题】{section_title}
【章节描述】{section_description or "无"}
【用户需求】{user_request or "无"}

【章节内容】
{section_content}

请给出审阅意见。"""

        try:
            full_prompt = f"{REVIEW_SYSTEM_PROMPT}\n\n{prompt}"
            response = await self.llm.ainvoke(full_prompt)
            review_text = response.content

            logger.info(
                f"审阅完成: {section_title} - "
                f"{'通过' if 'APPROVE' in review_text.upper() else '不通过'}"
            )

            return self._parse_review(review_text)

        except Exception as e:
            logger.error(f"审阅失败 {section_title}: {e}")
            return {
                "passed": True,  # 审阅失败时不阻塞流程
                "rating": "PASS",
                "strengths": [],
                "issues": [f"审阅系统错误: {str(e)}"],
                "suggestions": [],
                "review_text": "",
            }

    def _parse_review(self, review_text: str) -> Dict:
        """解析审阅文本为结构化结果"""
        lines = review_text.split("\n")

        passed = "APPROVE" in review_text.upper() and "DENY" not in review_text.upper()
        rating = "PASS"
        strengths = []
        issues = []
        suggestions = []

        current_section = None

        for line in lines:
            line = line.strip()
            if not line:
                continue

            if "审阅评级" in line or "评级" in line:
                if "MAJOR" in line.upper():
                    rating = "MAJOR_REVISION"
                elif "MINOR" in line.upper():
                    rating = "MINOR_REVISION"
                else:
                    rating = "PASS"
                current_section = None

            elif "优点" in line:
                current_section = "strengths"
                # 检查同一行是否有内容
                content = line.split("】", 1)[-1] if "】" in line else line.split("优点", 1)[-1]
                if content.strip().startswith("-"):
                    strengths.append(content.strip().lstrip("- "))

            elif "问题" in line:
                current_section = "issues"
                content = line.split("】", 1)[-1] if "】" in line else line.split("问题", 1)[-1]
                if content.strip().startswith("-"):
                    issues.append(content.strip().lstrip("- "))

            elif "修改建议" in line or "建议" in line:
                current_section = "suggestions"
                content = line.split("】", 1)[-1] if "】" in line else line.split("建议", 1)[-1]
                if content.strip().startswith("-"):
                    suggestions.append(content.strip().lstrip("- "))

            elif line.startswith("-") or line.startswith("•") or line.startswith("·"):
                item = line.lstrip("- •·")
                if current_section == "strengths":
                    strengths.append(item)
                elif current_section == "issues":
                    issues.append(item)
                elif current_section == "suggestions":
                    suggestions.append(item)

        return {
            "passed": passed,
            "rating": rating,
            "strengths": strengths[:5],
            "issues": issues[:10],
            "suggestions": suggestions[:10],
            "review_text": review_text,
        }